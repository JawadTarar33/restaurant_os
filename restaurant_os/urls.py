
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import *

router = DefaultRouter()

# Authentication
router.register(r'auth', AuthViewSet, basename='auth')

# Core Management
router.register(r'restaurants', RestaurantViewSet, basename='restaurants')
router.register(r'branches', BranchViewSet, basename='branches')
router.register(r'menu-items', MenuItemViewSet, basename='menu-items')

# POS
router.register(r'pos', POSViewSet, basename='pos')

# Finance & Analytics
router.register(r'finance', FinanceDashboardViewSet, basename='finance')
router.register(r'sales-analytics', SalesAnalyticsViewSet, basename='sales-analytics')

# AI Features
router.register(r'ai-forecast', AIForecastViewSet, basename='ai-forecast')
router.register(r'ai-comparison', AIComparisonViewSet, basename='ai-comparison')

# Inventory
router.register(r'inventory', InventoryViewSet, basename='inventory')
router.register(r'suppliers', SupplierViewSet, basename='suppliers')
router.register(r'inventory-orders', InventoryOrderViewSet, basename='inventory-orders')

urlpatterns = router.urls
