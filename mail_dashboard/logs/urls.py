from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('chart-data/', views.get_chart_data, name='chart_data'),
]