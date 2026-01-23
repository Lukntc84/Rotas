from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),

    path("login/", auth_views.LoginView.as_view(template_name="auth/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("painel/", include(("painel.urls", "painel"), namespace="painel")),
    path("gestao/", include(("gestao.urls", "gestao"), namespace="gestao")),
    path("", RedirectView.as_view(url="/painel/", permanent=False)),
    path("", include("django.contrib.auth.urls")),  # /password_reset/ etc
    path("accounts/", include("django.contrib.auth.urls")),
]
