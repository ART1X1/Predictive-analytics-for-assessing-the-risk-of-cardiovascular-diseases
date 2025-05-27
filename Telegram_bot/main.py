
import sqlite3
import nest_asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from catboost import CatBoostClassifier
import pandas as pd

bot = Bot('7629247815:AAFDwohea1Y3blp8eHo1frRdIbKN6LVMN_s')
nest_asyncio.apply()

class Mystate(StatesGroup):
    register = State()
    survey_start = State()
    survey = State()

conn = sqlite3.connect('database.sql')
cur = conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
cur.execute('''CREATE TABLE IF NOT EXISTS survey_results 
             (id INTEGER PRIMARY KEY, client_id INTEGER, age REAL, 
             ap_hi INTEGER, ap_lo INTEGER, cholesterol TEXT, 
             gluc TEXT, height INTEGER, weight INTEGER,
             prediction INTEGER, 
             FOREIGN KEY(client_id) REFERENCES clients(id))''')
conn.commit()
conn.close()

model = CatBoostClassifier()
model.load_model('/root/models/final_model.cbm')

start_markup = ReplyKeyboardMarkup(resize_keyboard=True)
start_markup.add(KeyboardButton('/start'))

survey_markup = ReplyKeyboardMarkup(resize_keyboard=True)
survey_markup.add(KeyboardButton('Yes'), KeyboardButton('No'))

cholesterol_markup = ReplyKeyboardMarkup(resize_keyboard=True)
cholesterol_markup.add(
    KeyboardButton('normal'),
    KeyboardButton('above normal'),
    KeyboardButton('well above normal')
)

gluc_markup = ReplyKeyboardMarkup(resize_keyboard=True)
gluc_markup.add(
    KeyboardButton('normal'),
    KeyboardButton('above normal'),
    KeyboardButton('well above normal')
)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer('''
Hi! I am a medical bot for cardiovascular risk assessment.
I can predict your risk and give recommendations.

Please, enter your name
''')
    await Mystate.register.set()

@dp.message_handler(state=Mystate.register)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Now enter your email:")
    await Mystate.next()

@dp.message_handler(state=Mystate.survey_start)
async def process_email(message: types.Message, state: FSMContext):
    await state.update_data(email=message.text)
    user_data = await state.get_data()

    conn = sqlite3.connect('database.sql')
    cur = conn.cursor()
    cur.execute("INSERT INTO clients (name, email) VALUES (?, ?)", (user_data['name'], user_data['email']))
    conn.commit()
    client_id = cur.lastrowid
    conn.close()

    await state.update_data(client_id=client_id)
    await message.answer("You have been successfully registered!\nWould you like to take a short health survey?", reply_markup=survey_markup)
    await Mystate.next()

questions = [
    "1. Enter your systolic blood pressure (top number, mmHg):",
    "2. Enter your age:",
    "3. Select your cholesterol level:",
    "4. Enter your diastolic blood pressure (bottom number, mmHg):",
    "5. Enter your weight (in kg):",
    "6. Enter your height (in cm):",
    "7. Select your blood glucose level:"
]

@dp.message_handler(lambda message: message.text.lower() == 'yes', state=Mystate.survey)
async def start_survey(message: types.Message, state: FSMContext):
    await state.update_data(current_question=0, answers={})
    await ask_next_question(message, state)

@dp.message_handler(lambda message: message.text.lower() == 'no', state=Mystate.survey)
async def decline_survey(message: types.Message, state: FSMContext):
    await message.answer("Okay, you can restart anytime with /start", reply_markup=start_markup)
    await state.finish()

async def ask_next_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    current_question = data.get('current_question', 0)

    if current_question < len(questions):
        if current_question == 2:
            await message.answer(questions[current_question], reply_markup=cholesterol_markup)
        elif current_question == 6:
            await message.answer(questions[current_question], reply_markup=gluc_markup)
        else:
            await message.answer(questions[current_question], reply_markup=ReplyKeyboardRemove())
    else:
        await process_survey_results(message, state)

@dp.message_handler(state=Mystate.survey)
async def handle_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    current_question = data.get('current_question', 0)
    answers = data.get('answers', {})

    try:
        if current_question == 0:
            val = int(message.text)
            if not 50 <= val <= 250:
                raise ValueError("Enter systolic pressure from 50 to 250")
            answers['ap_hi'] = val

        elif current_question == 1:
            val = float(message.text)
            if not 10 <= val <= 120:
                raise ValueError("Age must be between 10 and 120 years")
            answers['age'] = val

        elif current_question == 2:
            val = message.text.lower()
            if val not in ['normal', 'above normal', 'well above normal']:
                raise ValueError("Please use the keyboard to select a value")
            answers['cholesterol'] = val

        elif current_question == 3:
            val = int(message.text)
            if not 30 <= val <= 150:
                raise ValueError("Enter diastolic pressure from 30 to 150")
            answers['ap_lo'] = val

        elif current_question == 4:
            val = float(message.text)
            if not 20 <= val <= 300:
                raise ValueError("Weight should be from 20 to 300 kg")
            answers['weight'] = val

        elif current_question == 5:
            val = int(message.text)
            if not 50 <= val <= 250:
                raise ValueError("Height should be from 50 to 250 cm")
            answers['height'] = val

        elif current_question == 6:
            val = message.text.lower()
            if val not in ['normal', 'above normal', 'well above normal']:
                raise ValueError("Please use the keyboard to select a value")
            answers['gluc'] = val

        await state.update_data(answers=answers, current_question=current_question + 1)
        await ask_next_question(message, state)

    except Exception as e:
        await message.answer(f"Error: {e}")



async def process_survey_results(message: types.Message, state: FSMContext):
    data = await state.get_data()
    client_id = data['client_id']
    answers = data['answers']

    cholesterol_map = {'normal': 1, 'above normal': 2, 'well above normal': 3}
    gluc_map = {'normal': 1, 'above normal': 2, 'well above normal': 3}

    features = [
        answers['age'],
        answers['ap_hi'],
        cholesterol_map[answers['cholesterol']],
        answers['ap_lo'],
        gluc_map[answers['gluc']],
        answers['height'],
        answers['weight']
    ]

    input_df = pd.DataFrame([features], columns=[
        'age_new', 'ap_hi', 'cholesterol', 'ap_lo', 'gluc', 'height', 'weight'
    ])

    prediction = model.predict(input_df)[0]

    conn = sqlite3.connect('database.sql')
    cur = conn.cursor()
    cur.execute('''INSERT INTO survey_results 
        (client_id, age, ap_hi, ap_lo, cholesterol, gluc, height, weight, prediction)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (client_id, answers['age'], answers['ap_hi'], answers['ap_lo'],
         answers['cholesterol'], answers['gluc'], answers['height'],
         answers['weight'], prediction))
    conn.commit()
    conn.close()

    if prediction == 1:
        msg = '''You have an increased risk.

Recommendations:
1) Reduce your body weight, especially if you are overweight or obese. This will help reduce the load on your heart.
2) Increase physical activity: at least 30 minutes of moderate exercise (walking, swimming, exercise bike) 5 times a week.
3) Reduce your salt and sugar intake, avoid fatty, fried foods and fast food.
4) Undergo a medical examination - see a cardiologist for additional diagnostics.
5) Quit smoking and drinking alcohol - these are key risk factors that affect blood vessels and blood pressure.
        '''
    else:
        msg = '''Your risk is within the normal range.

Recommendations:
1) Continue to lead a healthy lifestyle - nutrition, exercise, quit bad habits.
2) Monitor your blood pressure - measure it at least once a year, even if there are no complaints.
3) Maintain a balanced diet: vegetables, fruits, whole grains, lean proteins.
4) Stay physically active - try to move for at least 30 minutes every day.
5) Avoid chronic stress - pay attention to rest, sleep and emotional state.
        '''

    await message.answer(msg, reply_markup=start_markup)
    await state.finish()



if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
