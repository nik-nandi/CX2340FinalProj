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

    # Itineraries routes
    path('itineraries/', views.itineraries_view, name='itineraries'),
    path('api/attractions/search/', views.search_attractions, name='search_attractions'),
    path('api/itinerary/add/', views.add_to_itinerary, name='add_to_itinerary'),
    path('api/itinerary/remove/<int:item_id>/', views.remove_from_itinerary, name='remove_from_itinerary'),
    path('api/itinerary/reorder/', views.reorder_itinerary, name='reorder_itinerary'),
    path('events/', views.local_events_list, name='local_events_list'),
    path('events/create/', views.create_local_event, name='create_local_event'),
]
