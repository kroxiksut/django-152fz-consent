from django import forms
from django.contrib import admin
from django.db import models

from .models import CertificateRequest, ContactMessage, Course, CourseSignup


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_active", "updated_at")
    search_fields = ("title", "slug")
    list_filter = ("is_active",)
    ordering = ("-is_active", "title")


@admin.register(CourseSignup)
class CourseSignupAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "course", "created_at")
    search_fields = ("full_name", "email", "phone")
    list_filter = ("course", "created_at")
    date_hierarchy = "created_at"
    list_select_related = ("course", "user")
    formfield_overrides = {
        models.TextField: {"widget": forms.Textarea(attrs={"rows": 4, "cols": 100})},
    }


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "created_at")
    search_fields = ("full_name", "email", "message")
    list_filter = ("created_at",)
    date_hierarchy = "created_at"
    formfield_overrides = {
        models.TextField: {"widget": forms.Textarea(attrs={"rows": 6, "cols": 100})},
    }


@admin.register(CertificateRequest)
class CertificateRequestAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "course_name", "created_at")
    search_fields = ("full_name", "email", "course_name")
    list_filter = ("created_at",)
    date_hierarchy = "created_at"
    list_select_related = ("user",)
    formfield_overrides = {
        models.TextField: {"widget": forms.Textarea(attrs={"rows": 4, "cols": 100})},
    }
