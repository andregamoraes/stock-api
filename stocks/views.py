from .services.polygon_client import PolygonClient
from .services.stock_service import get_payload_cached, bust_cache
from .models import Stock
from decimal import Decimal, InvalidOperation

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class StockView(APIView):
    """
    HTTP interface for reading a consolidated stock payload (GET)
    and recording a new purchase (POST).
    """
    def get(self, request, symbol):
        """
        Return the consolidated payload for `symbol`.

        The service returns a tuple (payload, http_status). We surface the exact
        status code, so client errors (e.g., bad ticker) and upstream failures
        (e.g., provider unavailable) are correctly reflected to the caller.
        """
        payload, http_status = get_payload_cached(symbol)
        return Response(payload, status=http_status)

    def post(self, request, symbol):
        """
        Record a new purchase for `symbol`.

        Behavior:
        - Validates `amount` is present and a positive number.
        - Resolves/validates the company name:
            * First tries our own DB (fast path).
            * Falls back to Polygon to validate the ticker and fetch the name.
              If Polygon is down, respond with 503; if ticker is invalid, 400.
        - Creates a new row (no upsert; historical log of purchases).
        - Busts the GET cache for this symbol to ensure subsequent reads include
          the new purchase immediately.
        """

        # Normalize the ticker for storage and lookups.
        symbol = symbol.upper()

        # Validate and parse `amount`
        raw = request.data.get("amount")
        if raw is None:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = Decimal(str(raw))
            if amount <= 0:
                return Response({"error": "amount must be > 0"}, status=status.HTTP_400_BAD_REQUEST)
        except (InvalidOperation, TypeError):
            return Response({"error": "amount must be a number"}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve company name.
        # Try DB first to avoid unnecessary upstream calls.
        company_name = Stock.objects.filter(company_code=symbol).values_list("company_name", flat=True).first()

        # If we don't have a name locally, validate the ticker upstream (Polygon).
        if not company_name:
            try:
                info = PolygonClient().get_company_info(symbol)
            except Exception as e:
                return Response({"error": "upstream provider unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            company_name = info.get("name")
            if not company_name:
                #If the provider responded but the name is absent, treat as invalid ticker.
                return Response({"error": "invalid or unknown ticker"}, status=status.HTTP_400_BAD_REQUEST)

        # Persist a new purchase entry
        Stock.objects.create(company_code=symbol, company_name=company_name, amount=amount)

        # Bust the cached GET payload so subsequent reads reflect this write.
        bust_cache(symbol)

        msg = f"{amount} units of stock {symbol} were added to your stock record"
        return Response(msg, status=status.HTTP_201_CREATED)

