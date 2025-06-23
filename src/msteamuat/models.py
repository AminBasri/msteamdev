# src/msteamuat/models.py
from pydantic import BaseModel

class ShiftReportOutput(BaseModel):
    subject: str
    body: str