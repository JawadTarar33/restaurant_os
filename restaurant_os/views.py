from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np

from .models import MenuItem, Sale, DailySale, Inventory, Supplier, InventoryOrder
from .serializers import (
    MenuItemSerializer, SaleSerializer, DailySaleSerializer,
    InventorySerializer, SupplierSerializer, InventoryOrderSerializer
)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer


class InventoryViewSet(viewsets.ModelViewSet):
    queryset = Inventory.objects.all()
    serializer_class = InventorySerializer

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        low_stock_items = self.get_queryset().filter(quantity__lte=models.F('reorder_level'))
        serializer = self.get_serializer(low_stock_items, many=True)
        return Response(serializer.data)


class InventoryOrderViewSet(viewsets.ModelViewSet):
    queryset = InventoryOrder.objects.all()
    serializer_class = InventoryOrderSerializer


class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer

    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Get top 5 popular menu items"""
        popular_items = self.get_queryset().order_by('-popularity_score')[:5]
        serializer = self.get_serializer(popular_items, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def predict_weekly_demand(self, request):
        """Predict demand for each item for the next 7 days using linear regression."""
        predictions = {}
        for item in MenuItem.objects.all():
            sales = Sale.objects.filter(menu_item=item).order_by('timestamp')
            if sales.count() < 3:
                continue

            df = pd.DataFrame(list(sales.values('timestamp', 'quantity')))
            df['day'] = df['timestamp'].dt.dayofyear
            X = df[['day']]
            y = df['quantity']
            model = LinearRegression()
            model.fit(X, y)

            next_week_days = np.array([df['day'].max() + i for i in range(1, 8)]).reshape(-1, 1)
            predicted_qty = model.predict(next_week_days).clip(min=0).round().tolist()
            predictions[item.name] = predicted_qty

        return Response(predictions)


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer


class DailySaleViewSet(viewsets.ModelViewSet):
    queryset = DailySale.objects.all()
    serializer_class = DailySaleSerializer

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get sales summary for the last 7 days"""
        today = timezone.now().date()
        start_date = today - timedelta(days=7)
        sales = DailySale.objects.filter(date__gte=start_date).order_by('date')
        serializer = self.get_serializer(sales, many=True)
        return Response(serializer.data)
