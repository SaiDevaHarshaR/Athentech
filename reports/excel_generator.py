import pandas as pd
from io import BytesIO

def create_excel(data: str, filename: str = "report.xlsx"):
    """
    Convert markdown table or data into Excel file.
    """
    try:
        # Simple way: if data is markdown table, better to pass DataFrame
        df = pd.read_csv(pd.StringIO(data), sep="|", engine="python")
        df = df.dropna(axis=1, how="all")
    except:
        # fallback
        df = pd.DataFrame({"Result": [data]})

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Report")
    output.seek(0)
    return output