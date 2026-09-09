"""
Tests for restock order API endpoints.
"""
import pytest
from datetime import date, timedelta


class TestGetRestockOrders:
    """Test suite for listing submitted restock orders."""

    def test_get_restock_orders_empty(self, client):
        """Test that no restock orders exist before any are submitted."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert data == []

    def test_get_restock_orders_newest_first(self, client):
        """Test that submitted orders are returned newest first."""
        first = client.post("/api/restock-orders", json={
            "budget": 10000,
            "items": [{"sku": "PRX-204", "quantity": 10}]
        })
        second = client.post("/api/restock-orders", json={
            "budget": 10000,
            "items": [{"sku": "MCU-402", "quantity": 10}]
        })
        assert first.status_code == 201
        assert second.status_code == 201

        response = client.get("/api/restock-orders")
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == second.json()["id"]
        assert data[1]["id"] == first.json()["id"]


class TestCreateRestockOrder:
    """Test suite for submitting a restock order."""

    def test_create_restock_order_success(self, client):
        """Test submitting a valid restock order returns 201 with full structure."""
        response = client.post("/api/restock-orders", json={
            "budget": 10000,
            "items": [{"sku": "PRX-204", "quantity": 900}]
        })
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert "id" in order
        assert "order_date" in order
        assert "expected_delivery" in order
        assert len(order["items"]) == 1

    def test_create_restock_order_recomputes_cost_from_inventory(self, client):
        """Test that total_cost is computed server-side from inventory unit_cost,
        not trusted from the client."""
        # PRX-204 unit_cost is 8.50 in inventory.json; 900 * 8.50 = 7650.0
        response = client.post("/api/restock-orders", json={
            "budget": 10000,
            "items": [{"sku": "PRX-204", "quantity": 900}]
        })
        assert response.status_code == 201

        order = response.json()
        assert abs(order["total_cost"] - 7650.0) < 0.01
        assert abs(order["items"][0]["unit_cost"] - 8.50) < 0.01
        assert abs(order["items"][0]["line_total"] - 7650.0) < 0.01

    def test_create_restock_order_lead_time_is_max_across_categories(self, client):
        """Test that lead_days reflects the slowest category in a mixed-category order."""
        # PRX-204 is Sensors (5 days), STP-303 is Actuators (21 days)
        response = client.post("/api/restock-orders", json={
            "budget": 50000,
            "items": [
                {"sku": "PRX-204", "quantity": 10},
                {"sku": "STP-303", "quantity": 10}
            ]
        })
        assert response.status_code == 201

        order = response.json()
        assert order["lead_days"] == 21

        order_date = date.fromisoformat(order["order_date"])
        expected_delivery = date.fromisoformat(order["expected_delivery"])
        assert expected_delivery == order_date + timedelta(days=21)

    def test_create_restock_order_appears_in_list(self, client):
        """Test that a submitted order is retrievable via GET."""
        create_response = client.post("/api/restock-orders", json={
            "budget": 10000,
            "items": [{"sku": "PRX-204", "quantity": 10}]
        })
        order_id = create_response.json()["id"]

        list_response = client.get("/api/restock-orders")
        data = list_response.json()
        assert len(data) == 1
        assert data[0]["id"] == order_id


class TestRestockOrderValidation:
    """Test suite for restock order validation and error handling."""

    def test_create_restock_order_empty_items(self, client):
        """Test that an order with no items is rejected."""
        response = client.post("/api/restock-orders", json={
            "budget": 10000,
            "items": []
        })
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_create_restock_order_unknown_sku(self, client):
        """Test that an order referencing a nonexistent SKU is rejected."""
        response = client.post("/api/restock-orders", json={
            "budget": 10000,
            "items": [{"sku": "NOT-A-REAL-SKU", "quantity": 10}]
        })
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_create_restock_order_zero_quantity(self, client):
        """Test that a non-positive quantity is rejected."""
        response = client.post("/api/restock-orders", json={
            "budget": 10000,
            "items": [{"sku": "PRX-204", "quantity": 0}]
        })
        assert response.status_code == 400

    def test_create_restock_order_over_budget(self, client):
        """Test that an order whose recomputed cost exceeds the stated budget is rejected."""
        # PRX-204 unit_cost 8.50 * 900 = 7650.0, well over a $100 budget
        response = client.post("/api/restock-orders", json={
            "budget": 100,
            "items": [{"sku": "PRX-204", "quantity": 900}]
        })
        assert response.status_code == 400

    def test_create_restock_order_malformed_body(self, client):
        """Test that a malformed request body is rejected with a validation error."""
        response = client.post("/api/restock-orders", json={
            "budget": "not-a-number",
            "items": "not-a-list"
        })
        assert response.status_code == 422
