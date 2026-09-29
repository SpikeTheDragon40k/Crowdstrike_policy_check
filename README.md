# CrowdStrike Prevention Policy Comparison

Export prevention policies from CrowdStrike Falcon Flight Control child CIDs, compare `Phase 3` policies with a JSON settings matrix, and generate CSV reports grouped by customer.

The scripts are read-only: they do not modify Falcon policies.

## Requirements

- Python 3
- A Falcon API client created in the parent CID
- `Flight Control: Read` and `Prevention Policies: Read` permissions

Install the dependencies:

```bash
python3 -m pip install crowdstrike-falconpy python-dotenv
```

## Configuration

Create a `.env` file in the project directory:

```dotenv
FALCON_CLIENT_ID=your_parent_client_id
FALCON_CLIENT_SECRET=your_parent_client_secret
```

Create or edit `phase3_matrix.json` with the expected values for each setting ID:

```json
{
  "SensorTamperingProtection": {
    "configured": true,
    "enabled": true
  },
  "CloudAntiMalware": {
    "detection": "AGGRESSIVE",
    "prevention": "AGGRESSIVE"
  }
}
```

These are example values. Use the settings and expected values from your approved baseline.

## Run

Run the complete workflow:

```bash
python3 workflow.py
```

It executes the scripts in order:

1. `parent-script.py` exports prevention policies from each child CID into `exports/`.
2. `comparatore.sh` compares `Phase 3` policies against `phase3_matrix.json` and creates `phase3_diff.json`.
3. `policy_csv_comparison.py` creates customer-grouped CSV reports in `customer_report/`.

`comparatore.sh` contains Python code despite its `.sh` extension. Run it with Python, not Bash.

You can also run each step manually:

```bash
python3 parent-script.py
python3 comparatore.sh ./exports/ --matrix phase3_matrix.json --output phase3_diff.json
python3 policy_csv_comparison.py phase3_diff.json --output-dir customer_report/
```

The workflow deletes existing `exports/`, `customer_report/`, and `phase3_diff.json` before starting. Back up anything in those locations that you need to retain.

## Output

- `exports/<child_cid>_prevention_policies.json`: policy exports and Flight Control child metadata.
- `phase3_diff.json`: comparison results, including expected and actual setting values.
- `customer_report/<customer_name>_diff.csv`: one CSV per customer with differences.

Customer names come from Flight Control child metadata. If a readable name is unavailable, the report uses `UNKNOWN CUSTOMER`.
