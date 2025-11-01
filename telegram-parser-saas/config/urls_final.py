from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from apps.users import views as user_views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Authentication
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('signup/', user_views.signup, name='signup'),
    
    # User profile
    path('profile/', user_views.profile, name='profile'),
    
    # Dashboard
    path('', include('apps.dashboard.urls')),
]

# Admin site customization
admin.site.site_header = "Telegram Parser SaaS"
admin.site.site_title = "Telegram Parser Admin"
admin.site.index_title = "Добро пожаловать в админ панель"
