from django.contrib import admin
from .models import Stock

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display  = ("company_code", "company_name", "amount", "created_at")
    search_fields = ("company_code", "company_name")
    list_filter   = ("company_code",)
    ordering      = ("-id",)

