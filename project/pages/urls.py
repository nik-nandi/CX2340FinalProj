from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),

    # Auth routes
    path('login/', auth_views.LoginView.as_view(template_name='pages/registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('signup/', views.signup_view, name='signup'),
    
    # Profile route
    path('accounts/profile/', views.profile_view, name='profile'),
    
    # Map UI route
    path('map/', views.map_ui, name='map_ui'),
]
