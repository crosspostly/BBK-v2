
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def list_worksheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("Панда Ролс")
        worksheets = spreadsheet.worksheets()
        
        print("Найдены следующие листы в таблице 'Панда Ролс':")
        for worksheet in worksheets:
            print(f"- {worksheet.title}")
            
    except gspread.exceptions.SpreadsheetNotFound:
        print("Ошибка: Таблица 'Панда Ролс' не найдена. Убедитесь, что вы поделились таблицей с email'ом сервисного аккаунта.")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    list_worksheets()
