
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def read_headers():
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        
        worksheet_name = "Расписание"
        worksheet = client.open("Панда Ролс").worksheet(worksheet_name)
        
        headers = worksheet.row_values(1)
        
        print(f"Заголовки на листе '{worksheet_name}':")
        print(headers)
        
    except gspread.exceptions.WorksheetNotFound:
        print(f"Ошибка: Лист '{worksheet_name}' не найден.")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    read_headers()
