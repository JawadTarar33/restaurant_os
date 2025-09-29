from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Menu, Sales
from .serializers import MenuSerializer, SalesSerializer
from .analytics import forecast_sales
class MenuViewSet(viewsets.ModelViewSet):
    serializer_class = MenuSerializer

    def get_queryset(self):
        return Menu.objects.filter(active=True)


class SalesViewSet(viewsets.ModelViewSet):
    queryset = Sales.objects.all()
    serializer_class = SalesSerializer



class SalesForecastViewSet(viewsets.ViewSet):

    # GET /forecast/
    def list(self, request):
        periods = int(request.GET.get("days", 30))
        forecast = forecast_sales(None, periods)

        if forecast is None:
            return Response({"error": "No sales data available"}, status=status.HTTP_400_BAD_REQUEST)

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