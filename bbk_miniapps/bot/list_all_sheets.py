import gspread
from oauth2client.service_account import ServiceAccountCredentials

def list_all_spreadsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        
        # List all spreadsheets available to the service account
        spreadsheets = client.openall()
        
        print("Доступные таблицы:")
        for sheet in spreadsheets:
            print(f"Название: '{sheet.title}' | ID: {sheet.id}")
            
    except Exception as e:
        print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    list_all_spreadsheets()
