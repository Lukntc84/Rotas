# rotas/services/geocode.py
import re
import requests

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"

HEADERS = {
    "User-Agent": "rotas_cd/1.0 (contato: cadastro01@lojasmarkem.com.br)",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

def _limpa_query(q: str) -> str:
    q = (q or "").strip()

    # Expande abreviações comuns (ajuda muito)
    q = re.sub(r"\bR\.", "Rua", q)
    q = re.sub(r"\bAv\.", "Avenida", q)


    # remove espaços duplicados
    q = re.sub(r"\s+", " ", q)
    return q

def _pick_best(results, expected_number: str = ""):
    if not results:
        return None

    expected_number = (expected_number or "").strip()

    # 1) se tiver número, prioriza quem bate house_number
    if expected_number:
        for item in results:
            addr = item.get("address") or {}
            hn = (addr.get("house_number") or "").strip()
            if hn == expected_number:
                return item

    # 2) prioriza tipos que costumam ser “ponto” (mais preciso)
    preferred_types = {"house", "building", "entrance", "address"}
    for item in results:
        t = (item.get("type") or "").lower()
        if t in preferred_types:
            return item

    # 3) fallback: maior importance
    results_sorted = sorted(results, key=lambda x: float(x.get("importance") or 0), reverse=True)
    return results_sorted[0]

def geocode_nominatim(query: str, *, expected_number: str = "", debug: bool = False):
    query = _limpa_query(query)
    if not query:
        return None

    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5,
        "countrycodes": "br",
    }

    r = requests.get(NOMINATIM_SEARCH, params=params, headers=HEADERS, timeout=25)

    if debug:
        print("STATUS:", r.status_code)
        print("URL:", r.url)
        print("BODY:", r.text[:300])

    if r.status_code != 200:
        return None

    data = r.json()
    if not data:
        return None

    best = _pick_best(data, expected_number=expected_number)
    if not best:
        return None

    lat = float(best["lat"])
    lon = float(best["lon"])
    display_name = best.get("display_name") or ""
    addr = best.get("address") or {}

    return lat, lon, display_name, addr

def endereco_curto(addr: dict) -> str:
    """
    Monta um endereço curto e bom pra UI (evita texto gigante do display_name).
    """
    if not addr:
        return ""

    road = addr.get("road") or addr.get("pedestrian") or addr.get("path") or ""
    house = addr.get("house_number") or ""
    suburb = addr.get("suburb") or addr.get("neighbourhood") or ""
    city = addr.get("city") or addr.get("town") or addr.get("village") or ""
    state = addr.get("state") or ""
    postcode = addr.get("postcode") or ""

    linha1 = ", ".join([p for p in [road, house] if p])
    linha2 = " - ".join([p for p in [suburb, city] if p]).strip()
    linha3 = " / ".join([p for p in [state, postcode] if p]).strip()

    partes = [p for p in [linha1, linha2, linha3] if p]
    return " | ".join(partes)[:255]


def _limpa_complementos(query: str) -> str:
    """
    Remove termos que atrapalham o Nominatim (shopping, brasil, etc).
    Mantém rua + número + cidade/uf + cep.
    """
    q = _limpa_query(query)

    # remove "Brasil" e coisas depois (normalmente só polui)
    q = re.sub(r",?\s*Brasil\s*$", "", q, flags=re.I)

    # remove blocos comuns de complemento que atrapalham
    # ex: ", Shopping Embu, Chácaras São Marcos,"
    q = re.sub(r",\s*Shopping[^,]*", "", q, flags=re.I)
    q = re.sub(r",\s*Ch[aá]caras[^,]*", "", q, flags=re.I)

    # remove espaços / vírgulas duplicadas
    q = re.sub(r"\s*,\s*", ", ", q)
    q = re.sub(r",\s*,", ",", q)
    q = re.sub(r"\s+", " ", q).strip(" ,")

    return q


def geocode_loja_com_fallback(loja, debug: bool = False):
    """
    Tenta geocodificar com 3 queries:
    1) loja.endereco (como está no banco)
    2) loja.endereco limpo (sem complementos)
    3) query curta e forte: logradouro + numero + cidade/uf + cep
    """
    tentativas = []

        # 0) tentativa estruturada (mais assertiva)
    if loja.logradouro or loja.endereco:
        street = f"{(loja.logradouro or '').strip()} {(loja.numero or '').strip()}".strip()
        city = (loja.cidade or "").strip()
        state = (loja.uf or "").strip()
        postalcode = (loja.cep or "").strip()

        if street and city:
            res = geocode_nominatim_structured(
                street=street,
                city=city,
                state=state,
                postalcode=postalcode,
                debug=debug
            )
            if res:
                return res
        
    
    if getattr(loja, "endereco", ""):
        tentativas.append(loja.endereco)

        limpo = _limpa_complementos(loja.endereco)
        if limpo and limpo != loja.endereco:
            tentativas.append(limpo)

    logradouro = (getattr(loja, "logradouro", "") or "").strip()
    numero = (getattr(loja, "numero", "") or "").strip()
    cidade = (getattr(loja, "cidade", "") or "").strip()
    uf = (getattr(loja, "uf", "") or "").strip()
    cep = (getattr(loja, "cep", "") or "").strip()

    curto = ", ".join([p for p in [
        " ".join([p for p in [logradouro, numero] if p]).strip(),
        " - ".join([p for p in [cidade, uf] if p]).strip(),
        cep
    ] if p])
    if curto:
        tentativas.append(curto)

    expected_number = (numero or "").strip()

    for q in tentativas:
        res = geocode_nominatim(q, expected_number=expected_number, debug=debug)
        if res:
            return res

    return None

def geocode_nominatim_structured(*, street="", city="", state="", postalcode="", debug=False):
    params = {
        "street": street,          # ex: "Rua Augusto de Almeida Batista 204"
        "city": city,              # "Embu das Artes"
        "state": state,            # "SP" ou "São Paulo"
        "postalcode": postalcode,  # "06814-010"
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 10,
        "countrycodes": "br",
    }

    r = requests.get(NOMINATIM_SEARCH, params=params, headers=HEADERS, timeout=25)

    if debug:
        print("STATUS:", r.status_code)
        print("URL:", r.url)
        print("BODY:", r.text[:300])

    if r.status_code != 200:
        return None

    data = r.json()
    if not data:
        return None

    # devolve o mais importante
    best = sorted(data, key=lambda x: float(x.get("importance") or 0), reverse=True)[0]
    lat = float(best["lat"])
    lon = float(best["lon"])
    display_name = best.get("display_name") or ""
    addr = best.get("address") or {}
    return lat, lon, display_name, addr