from challan_generator import generate_challan_pdf
from signal_state import trigger_green_corridor, get_signal_info, is_green_corridor_active

def test_all():
    test_alert = {
        "id": 42,
        "alert_type": "overspeed",
        "message": "Vehicle clocked at 98 km/h on Sector 4",
        "track_id": 7,
        "speed_kmh": 98.4,
        "camera_id": "camera_1",
        "status": "new",
        "plate_text": "DL01AB1234",
        "timestamp": "2026-09-14 18:30:00"
    }
    pdf_buf = generate_challan_pdf(test_alert)
    pdf_bytes = pdf_buf.read()
    print(f"Challan PDF generated: {len(pdf_bytes)} bytes, starts with: {pdf_bytes[:8]}")

    corridor = trigger_green_corridor("camera_1", duration_sec=10)
    print("Green Corridor triggered:", corridor)
    print("Signal Info:", get_signal_info("camera_1"))
    print("Is active:", is_green_corridor_active("camera_1"))
    print("ALL TESTS PASSED!")

if __name__ == "__main__":
    test_all()
