from django.urls import path, include
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect

# Главный URL для редиректа на dashboard
def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')
    else:
        return redirect('login')

urlpatterns = [
    # Django admin
    path('admin/', admin.site.urls),
    
    # Главная страница (редирект)
    path('', home_redirect, name='home'),
    
    # Аутентификация
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('signup/', include('apps.users.urls')),
    
    # Dashboard пользователя
    path('dashboard/', include('apps.dashboard.urls')),
    
    # API endpoints (если потребуется)
    path('api/', include('apps.telegram_parser.api_urls')),
]