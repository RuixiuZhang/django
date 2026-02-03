from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("conversations/", views.conversations, name="conversations"),
    path("c/<int:cid>/", views.chat_view, name="chat_view"),

    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),

    path("api/new/", views.api_new_conversation, name="api_new_conversation"),
    path("api/rename/", views.api_rename_conversation, name="api_rename_conversation"),
    path("api/delete/", views.api_delete_conversation, name="api_delete_conversation"),

    path("api/chat/", views.api_chat, name="api_chat"),
    path("api/chat/stream/", views.api_chat_stream, name="api_chat_stream"),

    path("_counselor/risk/", views.counselor_risk_dashboard),
    path("_counselor/c/<int:cid>/", views.counselor_conv_detail),
    path("_counselor/review/", views.counselor_review_submit),
    path("_counselor/send/", views.counselor_send),
    path("api/counselor/<int:cid>/", views.counselor_messages_api),
    path("readme/", views.readme_page),


]

