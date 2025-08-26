from django.contrib import admin
from django.urls import path, include
from stocks.views import StockView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/stock/<str:symbol>/", StockView.as_view()),
]
