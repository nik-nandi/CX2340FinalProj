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

    # Assistant routes
    path('assistant/', views.assistant, name='assistant'),
    path('api/assistant/ask/', views.ask_assistant, name='ask_assistant'),

    # Translator routes
    path('translator/', views.translator, name='translator'),
    path('api/translator/text/', views.translate_text, name='translate_text'),
    
    # Admin routes
    path('admin/edit_user/<int:user_id>/', views.admin_edit_user, name='admin_edit_user'), # New URL for editing users

    # Tour guide routes
    path('guides/create-tour/', views.create_tour_view, name='create_tour'),
    path('guides/my-tours/', views.my_tours_view, name='my_tours'),
    path('guides/edit-tour/<int:tour_id>/', views.edit_tour_view, name='edit_tour'),

    # Traveler routes for guides
    path('travelers/browse-guides/', views.browse_guides_view, name='browse_guides'),
    path('travelers/assign-guide/', views.assign_guide_view, name='assign_guide'),
    path('travelers/remove-guide/<int:trip_area_id>/', views.remove_guide_view, name='remove_guide'),

    # Inquiry management routes
    path('inquiries/send/', views.send_inquiry_view, name='send_inquiry'),
    path('inquiries/send/<int:trip_area_id>/', views.send_inquiry_view, name='send_inquiry_for_trip'),
    path('inquiries/my/', views.my_inquiries_view, name='my_inquiries'),
    path('guides/inbox/', views.guide_inbox_view, name='guide_inbox'),
    path('inquiries/detail/<int:inquiry_id>/', views.inquiry_detail_view, name='inquiry_detail'),
    path('api/inquiries/status/<int:inquiry_id>/', views.update_inquiry_status, name='update_inquiry_status'),

    # Bookmarks routes
    path('bookmarks/', views.bookmarks_view, name='bookmarks'),
    path('api/bookmarks/add/', views.add_bookmark, name='add_bookmark'),
    path('api/bookmarks/remove/<int:bookmark_id>/', views.remove_bookmark, name='remove_bookmark'),
    path('api/bookmarks/update-notes/', views.update_bookmark_notes, name='update_bookmark_notes'), # New URL for updating notes

    # Alerts routes
    path('trip/<int:trip_area_id>/alerts/', views.trip_alerts_view, name='trip_alerts'),
    path('guide/alerts/', views.guide_alerts_view, name='guide_alerts'),
    path('guide/alerts/create/', views.create_alert_view, name='create_alert'),
    path('guide/alerts/<int:alert_id>/edit/', views.edit_alert_view, name='edit_alert'),
    path('guide/alerts/<int:alert_id>/delete/', views.delete_alert_view, name='delete_alert'),

    # Review routes
    path('guides/<int:guide_id>/', views.guide_profile_view, name='guide_profile'),
    path('guides/<int:guide_id>/review/', views.submit_review_view, name='submit_review'),
    path('reviews/my/', views.my_reviews_view, name='my_reviews'),
    path('guides/reviews/', views.guide_reviews_view, name='guide_reviews'),
]
