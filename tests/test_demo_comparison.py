from frontend.demo_comparison import calculate_demo_summary, get_demo_listings


def test_demo_comparison_calculates_lowest_highest_and_savings():
    listings = get_demo_listings()
    summary = calculate_demo_summary(listings)

    assert [(item["retailer"], item["price"]) for item in listings] == [
        ("Blinkit", 65.0),
        ("Zepto", 62.0),
        ("Instamart", 68.0),
    ]
    assert summary == {
        "lowest_price": 62.0,
        "lowest_retailer": "Zepto",
        "highest_price": 68.0,
        "savings": 6.0,
    }


def test_demo_data_is_marked_simulated_and_has_no_persistence_identity():
    listings = get_demo_listings()
    assert all(item["source"] == "SIMULATED" for item in listings)
    assert all(item["currency"] == "INR" for item in listings)
    assert all(item["pincode"] == "121006" for item in listings)
    assert all(item["availability"] == "In stock" for item in listings)
    assert all(item["observed_at"] for item in listings)
    assert all("product_id" not in item and "history_id" not in item for item in listings)

    # The summary is a pure calculation over sample rows: it does not accept a
    # database session or tracked-product identifier and cannot save history.
    assert set(calculate_demo_summary(listings)) == {
        "lowest_price", "lowest_retailer", "highest_price", "savings"
    }
