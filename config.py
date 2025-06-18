import os
from dotenv import load_dotenv

load_dotenv()

email_accounts = [
    {
        "companyId": int(os.getenv("COMPANY_ID_1", "1")),
        "companyBranchId": int(os.getenv("COMPANY_BRANCH_ID_1", "2")),
        "financialYearId": int(os.getenv("FINANCIAL_YEAR_ID_1", "3")),
        "clientId": int(os.getenv("CLIENT_ID_1", "7")),
        "id": int(os.getenv("ID_1", "6")),
        "user": os.getenv("EMAIL_USER_1"),
        "password": os.getenv("EMAIL_PASSWORD_1"),
        "imap_url": os.getenv("IMAP_URL_1", "imap.gmail.com")
    },
    {
        "companyId": int(os.getenv("COMPANY_ID_2", "2")),
        "companyBranchId": int(os.getenv("COMPANY_BRANCH_ID_2", "4")),
        "financialYearId": int(os.getenv("FINANCIAL_YEAR_ID_2", "3")),
        "clientId": int(os.getenv("CLIENT_ID_2", "9")),
        "id": int(os.getenv("ID_2", "8")),
        "user": os.getenv("EMAIL_USER_2"),
        "password": os.getenv("EMAIL_PASSWORD_2"),
        "imap_url": os.getenv("IMAP_URL_2", "imap.gmail.com")
    },
    {
        "companyId": int(os.getenv("COMPANY_ID_3", "3")),
        "companyBranchId": int(os.getenv("COMPANY_BRANCH_ID_3", "3")),
        "financialYearId": int(os.getenv("FINANCIAL_YEAR_ID_3", "5")),
        "clientId": int(os.getenv("CLIENT_ID_3", "7")),
        "id": int(os.getenv("ID_3", "5")),
        "user": os.getenv("EMAIL_USER_3"),
        "password": os.getenv("EMAIL_PASSWORD_3"),
        "imap_url": os.getenv("IMAP_URL_3", "imap.gmail.com")
    }
]

email_accounts = [account for account in email_accounts 
                 if account["user"] and account["password"]]

if not email_accounts:
    raise ValueError("No valid email accounts found. Please check your .env file.")


