import os
import sys
import time
import datetime
import urllib.request
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models import OrderFlow, ProductionLog

BASE_URL = "http://127.0.0.1:8001"

def make_request(path, method="GET", data=None):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req_data = json.dumps(data).encode("utf-8")
    else:
        req_data = None
        
    try:
        with urllib.request.urlopen(req, data=req_data) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"Request failed: {method} {path} - {e}")
        raise e

def run_flow_tests():
    print("=" * 60)
    print("   OPERATOR-GUIDED PRODUCTION FLOW STATE MACHINE INTEGRATION TEST")
    print("=" * 60)

    # 1. Inject mock job pair
    print("\n[Step 1] Injecting mock OMA job pair...")
    res = make_request("/api/system/mock-job", "POST")
    job_id = res["job_id"]
    print(f"-> Created job pair with JOB ID: {job_id}")
    time.sleep(1.0) # Wait for folder monitor watchdog to process the files asynchronously

    # 2. Get initial flow status
    print("\n[Step 2] Verifying initial WAITING_RIGHT_LENS state...")
    flow = make_request(f"/api/orders/{job_id}/flow")
    print(f"-> Current State: {flow['state']}")
    assert flow["state"] == "WAITING_RIGHT_LENS"
    assert flow["od_status"] == "PENDING"
    assert flow["oe_status"] == "PENDING"
    print("[OK] Initial state verified.")

    # 3. Test Inactivity Warning trigger
    print("\n[Step 3] Testing inactivity warning log generation...")
    # Update last_activity to 40 seconds in the past to trigger timeout
    db = SessionLocal()
    try:
        of = db.query(OrderFlow).filter(OrderFlow.job_id == job_id).first()
        of.last_activity = datetime.datetime.utcnow() - datetime.timedelta(seconds=45)
        db.commit()
    finally:
        db.close()
        
    # Query with test_timeout=true
    flow = make_request(f"/api/orders/{job_id}/flow?test_timeout=true")
    # Verify warning log in timeline
    warning_logs = [log for log in flow["logs"] if log["event_type"] == "ERROR" and "inatividade" in log["message"]]
    print(f"-> Found warning logs: {len(warning_logs)}")
    assert len(warning_logs) > 0
    print(f"-> Warning Message: '{warning_logs[0]['message']}'")
    print("[OK] Inactivity warning logged successfully.")

    # 4. Start OD engraving
    print("\n[Step 4] Triggering start engraving for Right Lens (OD)...")
    flow = make_request(f"/api/orders/{job_id}/flow/start", "POST")
    print(f"-> New State: {flow['state']}")
    assert flow["state"] == "RIGHT_LENS_PROCESSING"
    assert flow["od_status"] == "PROCESSING"
    print("[OK] Right lens processing started.")

    # 5. Pause engraving
    print("\n[Step 5] Pausing engraving mid-way...")
    time.sleep(1.0)  # Wait for a couple of lines to be processed
    flow = make_request(f"/api/orders/{job_id}/flow/pause", "POST")
    print(f"-> New State: {flow['state']}")
    print(f"-> Pause Count: {flow['pause_count']}")
    print(f"-> Stopped Line Index: {flow['last_stopped_index']}")
    assert flow["state"] == "PAUSED"
    assert flow["pause_count"] == 1
    assert flow["last_stopped_index"] > 0
    print("[OK] Engraving paused successfully and state updated.")

    # 6. Resume engraving
    print("\n[Step 6] Resuming engraving...")
    flow = make_request(f"/api/orders/{job_id}/flow/resume", "POST")
    print(f"-> New State: {flow['state']}")
    assert flow["state"] == "RIGHT_LENS_PROCESSING"
    print("[OK] Engraving resumed successfully.")

    # 7. Monitor till complete (Right lens)
    print("\n[Step 7] Monitoring right lens engraving to completion...")
    max_wait = 30
    start_time = time.time()
    completed = False
    while time.time() - start_time < max_wait:
        flow = make_request(f"/api/orders/{job_id}/flow")
        if flow["state"] == "WAITING_RIGHT_REMOVAL":
            completed = True
            break
        print(f"   - Current State: {flow['state']}, OD Status: {flow['od_status']}")
        time.sleep(1.0)
        
    assert completed
    assert flow["od_status"] == "COMPLETED"
    print(f"[OK] Right lens completed and transitioned to WAITING_RIGHT_REMOVAL. Time taken: {time.time() - start_time:.1f}s")

    # 8. Confirm Removal
    print("\n[Step 8] Confirming removal of Right Lens...")
    flow = make_request(f"/api/orders/{job_id}/flow/confirm-removal", "POST")
    print(f"-> New State: {flow['state']}")
    assert flow["state"] == "WAITING_LEFT_LENS"
    print("[OK] Right lens removal confirmed. Stepper correctly advanced to WAITING_LEFT_LENS.")

    # 9. Skip Left Lens (OE)
    print("\n[Step 9] Skipping Left Lens...")
    flow = make_request(f"/api/orders/{job_id}/flow/skip", "POST")
    print(f"-> New State: {flow['state']}")
    assert flow["state"] == "COMPLETED"
    assert flow["oe_status"] == "SKIPPED"
    assert flow["skip_count"] == 1
    print("[OK] Left lens skipped. Flow marked COMPLETED.")

    # 10. Check Metrics
    print("\n[Step 10] Checking production metrics...")
    metrics = make_request("/api/production/metrics")
    print(f"-> Completed Orders: {metrics['completed_orders']}")
    print(f"-> Average Cycle Time: {metrics['average_cycle_time']}s")
    print(f"-> Total Pauses: {metrics['total_pause_count']}")
    print(f"-> Total Skips: {metrics['total_skip_count']}")
    assert metrics["completed_orders"] >= 1
    print("[OK] Production metrics updated correctly.")

    print("\n" + "=" * 60)
    print("   INTEGRATION TEST SUCCESS: ALL OPERATIONAL FLOW PATHS WORK PERFECTLY!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        run_flow_tests()
        sys.exit(0)
    except Exception as e:
        print(f"\nx TEST FAILED: {e}")
        sys.exit(1)
