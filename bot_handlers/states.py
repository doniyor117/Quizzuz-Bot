from aiogram.fsm.state import State, StatesGroup

class CreateSetState(StatesGroup):
    waiting_for_folder = State()
    waiting_for_name = State()
    waiting_for_category = State()
    adding_cards = State()

class CreateFolderState(StatesGroup):
    waiting_for_name = State()

class PracticeState(StatesGroup):
    selecting_set = State()
    config_mode = State()     
    active_practice = State() 

class ManageState(StatesGroup):
    browsing_folders = State()
    viewing_folder_options = State()
    renaming_folder = State()
    viewing_set_options = State() # Viewing a specific set to Delete/Move
    moving_set = State()          # Selecting the destination folder

class AdminState(StatesGroup):
    waiting_for_user_id = State()