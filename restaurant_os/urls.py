from django.urls import path, include
from .views import SalesForecastViewSet, MenuViewSet, SalesViewSet
from rest_framework import routers
forecast_list = SalesForecastViewSet.as_view({'get': 'list'})
forecast_detail = SalesForecastViewSet.as_view({'get': 'retrieve'})
router = routers.DefaultRouter()
router.register(r'menu', MenuViewSet, basename='menu')
router.register(r'sales', SalesViewSet, basename='sales')
urlpatterns = [
    path("forecast/", forecast_list, name="forecast_all"),
    path("forecast/<uuid:pk>/", forecast_detail, name="forecast_item"),
    path('', include(router.urls)),
]
