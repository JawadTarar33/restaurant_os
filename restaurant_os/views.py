from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Menu, Sales, SalesItem
from .serializers import MenuSerializer, SalesSerializer, SalesItemSerializer
from .analytics import forecast_sales

import io
import matplotlib.pyplot as plt
from django.http import HttpResponse


class MenuViewSet(viewsets.ModelViewSet):
    serializer_class = MenuSerializer

    def get_queryset(self):
        return Menu.objects.filter(active=True)


class SalesViewSet(viewsets.ModelViewSet):
    queryset = Sales.objects.all().prefetch_related('sale_items', 'sale_items__item')
    serializer_class = SalesSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        
        if start_date:
            queryset = queryset.filter(sale_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(sale_date__lte=end_date)
        
        return queryset.order_by('-sale_date')
    
    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        """Add a new item to an existing sale"""
        sale = self.get_object()
        
        item_id = request.data.get('item')
        quantity = request.data.get('quantity')
        discount = request.data.get('discount', 0.0)
        
        try:
            menu_item = Menu.objects.get(id=item_id, active=True)
        except Menu.DoesNotExist:
            return Response(
                {"error": "Menu item not found or inactive"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        sale_item = SalesItem.objects.create(
            sale=sale,
            item=menu_item,
            quantity=quantity,
            price_per_unit=menu_item.sales_price,
            discount=discount
        )
        
        sale.calculate_totals()
        
        return Response(
            SalesItemSerializer(sale_item).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['delete'])
    def remove_item(self, request, pk=None):
        """Remove an item from a sale"""
        sale = self.get_object()
        item_id = request.data.get('item_id')
        
        try:
            sale_item = SalesItem.objects.get(id=item_id, sale=sale)
            sale_item.delete()
            sale.calculate_totals()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except SalesItem.DoesNotExist:
            return Response(
                {"error": "Sale item not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class SalesForecastViewSet(viewsets.ViewSet):

    # GET /forecast/
    def list(self, request):
        periods = int(request.query_params.get("periods", 30))
        item_id = request.query_params.get("item_id", None)

        forecast = forecast_sales(item_id, periods)

        if forecast is None:
            return Response({"detail": "No sales data available"}, status=404)

        result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].to_dict(orient="records")

        return Response(result)

    # GET /forecast/<uuid:item_id>/
    def retrieve(self, request, pk=None):
        periods = int(request.GET.get("days", 30))
        forecast = forecast_sales(pk, periods)

        if forecast is None:
            return Response({"error": "No sales data available"}, status=status.HTTP_400_BAD_REQUEST)

        result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].to_dict(orient="records")
        return Response(result)
    
    def forecast_plot(request):
        forecast = forecast_sales(periods=30)
        if forecast is None:
            return HttpResponse("No data")

        # Make the plot
        plt.figure(figsize=(12,6))
        plt.plot(forecast["ds"], forecast["yhat"], label="Forecast", color="blue")
        plt.fill_between(forecast["ds"], forecast["yhat_lower"], forecast["yhat_upper"], 
                        color="skyblue", alpha=0.3)
        plt.legend()
        plt.xticks(rotation=45)
        plt.title("Sales Forecast")

        # Save to PNG buffer
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)

        return HttpResponse(buf.getvalue(), content_type="image/png")