from django.conf import settings
from django.db import models

class Conversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=120, default="新对话")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.id}:{self.title}"

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16)
    sender = models.CharField(max_length=64, blank=True, default="")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["conversation", "created_at"])]

class RiskEvent(models.Model):
    LEVELS = [("LOW","LOW"), ("MEDIUM","MEDIUM"), ("HIGH","HIGH")]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="risk_events"
    )
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="risk_event"
    )
    level = models.CharField(max_length=8, choices=LEVELS)
    tags = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["level", "created_at"]),
            models.Index(fields=["conversation", "created_at"]),
        ]

class RiskReview(models.Model):
    STATUS = [
        ("OPEN","OPEN"),
        ("REVIEWED","REVIEWED"),
        ("FOLLOW_UP","FOLLOW_UP"),
        ("CLOSED","CLOSED"),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="risk_reviews"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=16, choices=STATUS, default="OPEN")
    note = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
