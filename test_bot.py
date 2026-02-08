import logging
from unittest.mock import MagicMock, AsyncMock
import asyncio

# Setup logging for the test
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Mock the telegram modules before importing the bot script
import sys
from types import ModuleType

# Create mock modules for telegram and its submodules
mock_telegram = ModuleType('telegram')
sys.modules['telegram'] = mock_telegram
mock_telegram.Update = MagicMock()
mock_telegram.InlineKeyboardButton = MagicMock()
mock_telegram.InlineKeyboardMarkup = MagicMock()

mock_telegram_ext = ModuleType('telegram.ext')
sys.modules['telegram.ext'] = mock_telegram_ext
mock_telegram_ext.Application = MagicMock()
mock_telegram_ext.CommandHandler = MagicMock()
mock_telegram_ext.ContextTypes = MagicMock()
mock_telegram_ext.ConversationHandler = MagicMock()
mock_telegram_ext.MessageHandler = MagicMock()
mock_telegram_ext.filters = MagicMock()
mock_telegram_ext.CallbackQueryHandler = MagicMock()

mock_telegram_constants = ModuleType('telegram.constants')
sys.modules['telegram.constants'] = mock_telegram_constants
mock_telegram_constants.ChatAction = MagicMock()


# Now, import the functions from the bot script
from telegram_bot import get_sheet, show_available_dates, book_slot, CHOOSE_DATE, ConversationHandler

# --- Test Runner ---
class BotTester:
    def __init__(self):
        self.sheet = get_sheet()
        self.test_user_id = 12345
        self.test_username = "test_user"
        logging.info("BotTester initialized and connected to Google Sheet.")

    async def run_all_tests(self):
        logging.info("--- Starting Full Bot Analysis ---")
        if not self.sheet:
            logging.error("Cannot run tests: Failed to connect to Google Sheet.")
            return

        test_date = await self.test_1_find_available_date()
        if not test_date:
            logging.warning("Skipping booking tests as no available date was found.")
            await self.cleanup_full_date_test() # Still run cleanup for general safety in case a previous test left something
            logging.info("--- Full Bot Analysis Finished ---")
            return

        await self.test_2_book_first_slot(test_date)
        await self.test_3_book_second_slot(test_date)
        await self.test_4_handle_full_date() # This test performs its own cleanup internally
        await self.cleanup_booking_tests(test_date) # Cleanup for test_2 and test_3
        
        logging.info("--- Full Bot Analysis Finished ---")

    async def test_1_find_available_date(self):
        logging.info("TEST 1: Finding an available date...")
        mock_update = self._create_mock_update()
        mock_context = self._create_mock_context()
        
        # We need to simulate the callback query part
        mock_update.callback_query = AsyncMock()
        mock_update.callback_query.answer = AsyncMock()
        mock_update.callback_query.edit_message_text = AsyncMock()
        mock_update.effective_chat.id = 123
        
        result = await show_available_dates(mock_update, mock_context)

        if result == CHOOSE_DATE:
            available_dates = mock_context.user_data["available_dates"]
            logging.info(f"SUCCESS: Found available dates: {available_dates}")
            if available_dates:
                return available_dates[0]
            else:
                logging.warning("No available dates found, but test passed because the bot returned CHOOSE_DATE.")
                return None
        else:
            logging.error("FAILURE: Could not find any available dates to run tests.")
            return None

    async def test_2_book_first_slot(self, test_date):
        logging.info(f"TEST 2: Booking first slot on date: {test_date}...")
        
        cell_date = self.sheet.find(test_date)
        row_index = cell_date.row
        
        # Get initial state of the row (A to E)
        initial_cells = self.sheet.range(f'A{row_index}:E{row_index}')
        initial_values = [cell.value for cell in initial_cells]

        mock_update = self._create_mock_update(text=test_date)
        mock_context = self._create_mock_context(available_dates=[test_date])

        result = await book_slot(mock_update, mock_context)
        
        # Verify the sheet was updated
        updated_cells = self.sheet.range(f'A{row_index}:E{row_index}')
        updated_values = [cell.value for cell in updated_cells]
        expected_entry = f"@{self.test_username} (ID: {self.test_user_id})"
        
        if result == ConversationHandler.END:
            updated_column_index = -1
            for i in range(1, 5): # Check columns B, C, D, E (indices 1 to 4)
                if initial_values[i] == '' and updated_values[i] == expected_entry:
                    updated_column_index = i
                    break
            
            if updated_column_index != -1:
                logging.info(f"SUCCESS: Booked first slot. '{expected_entry}' was written to column {chr(ord('A') + updated_column_index)}.")
            else:
                logging.error("FAILURE: Booking seemed to succeed, but couldn't verify the change in columns B-E. Initial: %s, Updated: %s", initial_values, updated_values)
        else:
            logging.error("FAILURE: book_slot did not return END.")

    async def test_3_book_second_slot(self, test_date):
        logging.info(f"TEST 3: Booking second slot on date: {test_date}...")
        
        cell_date = self.sheet.find(test_date)
        row_index = cell_date.row
        initial_cells = self.sheet.range(f'A{row_index}:E{row_index}')
        initial_values = [cell.value for cell in initial_cells]

        mock_update = self._create_mock_update(text=test_date, user_id=67890, username="test_user_2")
        mock_context = self._create_mock_context(available_dates=[test_date])

        result = await book_slot(mock_update, mock_context)

        updated_cells = self.sheet.range(f'A{row_index}:E{row_index}')
        updated_values = [cell.value for cell in updated_cells]
        new_entry = "@test_user_2 (ID: 67890)"
        
        if result == ConversationHandler.END:
            first_entry = f"@{self.test_username} (ID: {self.test_user_id})"
            if new_entry in updated_values and first_entry in updated_values:
                 # Ensure a new slot was filled and not an existing one overwritten
                 new_slot_filled = False
                 for i in range(1, 5):
                     if initial_values[i] == '' and updated_values[i] == new_entry:
                         new_slot_filled = True
                         break
                 if new_slot_filled:
                     logging.info(f"SUCCESS: Second slot booked without overwriting the first.")
                 else:
                     logging.error("FAILURE: Second booking did not fill a new slot, or overwritten existing.")
            else:
                 logging.error("FAILURE: Second booking failed to appear in sheet, or first entry was removed.")
        else:
            logging.error("FAILURE: book_slot for second entry did not return END.")


    async def test_4_handle_full_date(self):
        logging.info("TEST 4: Handling a fully booked date...")
        target_row_index = self._find_first_available_row()
        if not target_row_index:
            logging.warning("Skipping TEST 4: No available row to create a full date scenario.")
            return

        # Fetch original values for columns A-E
        original_cells = self.sheet.range(f'A{target_row_index}:E{target_row_index}')
        original_values = [cell.value for cell in original_cells]
        
        full_date_str = original_values[0]
        logging.info(f"Using date '{full_date_str}' in row {target_row_index} for this test.")
        
        # Fill all 4 slots (B-E) to make it full
        update_range = self.sheet.range(f'B{target_row_index}:E{target_row_index}')
        for cell in update_range:
            cell.value = 'full_by_test'
        self.sheet.update_cells(update_range)
        await asyncio.sleep(1) # Give GSheets time to propagate changes
        # Force a fresh sheet object to ensure updated values are read
        self.sheet = get_sheet()
        
        # Now check if this date is listed as available by the bot
        mock_update = self._create_mock_update()
        mock_context = self._create_mock_context()
        mock_update.callback_query = AsyncMock()
        mock_update.callback_query.answer = AsyncMock()
        mock_update.callback_query.edit_message_text = AsyncMock()
        mock_update.effective_chat.id = 123 # Needs to be set for send_chat_action
        
        await show_available_dates(mock_update, mock_context)
        
        available_dates = mock_context.user_data.get("available_dates", [])
        if full_date_str not in available_dates:
            logging.info(f"SUCCESS: The fully booked date '{full_date_str}' was not listed as available.")
        else:
            logging.error(f"FAILURE: The fully booked date '{full_date_str}' was incorrectly listed as available. Available dates: {available_dates}")

        # Cleanup: Restore original values for columns B-E
        cleanup_range = self.sheet.range(f'B{target_row_index}:E{target_row_index}')
        for i, cell in enumerate(cleanup_range):
            cell.value = original_values[i + 1] # +1 because original_values includes A column
        self.sheet.update_cells(cleanup_range)
        logging.info(f"Cleanup for TEST 4: Restored row {target_row_index} values to original.")


    async def cleanup_booking_tests(self, test_date):
        logging.info(f"CLEANUP for booking tests: Removing test entries for date '{test_date}'...")
        try:
            cell_date = self.sheet.find(test_date)
            row_index = cell_date.row
            
            # Find all cells with test user entries in that row and clear them
            test_entries_identifiers = [self.test_username, "test_user_2"]
            
            row_cells = self.sheet.range(f'A{row_index}:E{row_index}')
            for cell in row_cells[1:5]: # Only check columns B-E
                for identifier in test_entries_identifiers:
                    if identifier in cell.value:
                        cell.value = ""
            self.sheet.update_cells(row_cells[1:5]) # Update only B-E
            logging.info("Cleanup of booking tests complete.")
        except gspread.exceptions.CellNotFound:
            logging.warning("Could not find test date for cleanup. It might have been modified during tests.")
        except Exception as e:
            logging.error(f"An error occurred during cleanup: {e}")

    async def cleanup_full_date_test(self):
        logging.info("CLEANUP for full date test: Checking for 'full_by_test' entries and clearing them...")
        try:
            full_cells = self.sheet.findall('full_by_test')
            if full_cells:
                logging.info(f"Found {len(full_cells)} cells filled by test_4. Clearing them.")
                for cell in full_cells:
                    self.sheet.update_acell(cell.address, '')
                logging.info("Cleaned up 'full_by_test' entries.")
        except Exception as e:
            logging.error(f"An error occurred during full date cleanup: {e}")


    def _find_first_available_row(self):
        # This is for TEST 4 to find a row to make full.
        # It needs to return the row index.
        all_data = self.sheet.get_all_values()
        for i, row in enumerate(all_data[1:], start=2): # Start from the second row (index 1 of all_data)
             padded_row = row + [''] * max(0, 5 - len(row))
             if any(cell_value == '' for cell_value in padded_row[1:5]):
                 return i # Return 1-based row index
        return None


    def _create_mock_update(self, text=None, user_id=None, username=None):
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = text
        update.message.from_user = MagicMock()
        update.message.from_user.id = user_id if user_id is not None else self.test_user_id
        update.message.from_user.username = username if username is not None else self.test_username
        
        # Ensure reply_text is an AsyncMock
        update.message.reply_text = AsyncMock()
        
        return update

    def _create_mock_context(self, available_dates=None):
        context = MagicMock()
        context.user_data = {"available_dates": available_dates} if available_dates else {}
        context.bot = MagicMock()
        context.bot.send_chat_action = AsyncMock()
        return context

if __name__ == "__main__":
    tester = BotTester()
    asyncio.run(tester.run_all_tests())