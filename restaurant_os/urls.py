from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MenuViewSet, SalesViewSet, SalesForecastViewSet

router = DefaultRouter()
router.register(r'menu', MenuViewSet, basename='menu')
router.register(r'sales', SalesViewSet, basename='sales')
router.register(r'forecast', SalesForecastViewSet, basename='forecast')

urlpatterns = [
    path('', include(router.urls)),
]