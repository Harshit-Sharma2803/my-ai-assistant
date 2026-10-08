import os
import json
from dotenv import load_dotenv
from google import genai

# Load the hidden .env file
load_dotenv()

# Get the API key
api_key = os.getenv("GEMINI_API_KEY")

# Create Gemini client
client = genai.Client(api_key=api_key)

#Create a Chat
chat = client.chats.create(
    model="gemini-3.6-flash"
)

#History List
history = []
HISTORY_FILE = "chat_history.json"
#memory file which stores important things about user
MEMORY_FILE = "memory.json"

#it loads our history of chats
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as file:
        history = json.load(file)

#it loads our memory of chats
memory = {}
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r") as file:
        memory = json.load(file)


print("Note➡️ : For any type of help type /help")

def create_chat_with_history():
    chat = client.chats.create(
        model = "gemini-3.6-flash"
    )

    return chat

chat = create_chat_with_history()

#to get the memory of our conversation
def get_memory_context():

    if not memory:
        return ""

    context = "Here is some information remembered about the user:\n"

    for key, value in memory.items():
        context += f"- {key}: {value}\n"

    return context

#to get automatically detect useful info
def save_memory(key,value):

    memory[key] = value

    with open(MEMORY_FILE,"w")as file:
        json.dump(memory,file,indent=4)

    print(f"🧠 Memory saved: {key} = {value}")



while True:

    question = input("Ask your question: ")

    

     #exit command
    if question.lower() == "exit":
        print("Thank you! Have a nice day 😊")
        break

    #for store in memory
    elif question.lower().startswith("/remember "):
        data = question[10:]

        if "=" in data:
            key, value = data.split("=",1)

            key = key.strip()
            value = value.strip()

            memory[key] = value

            with open(MEMORY_FILE, "w") as file:
                json.dump(memory,file,indent = 4)

            print(f"🧠 Remembered: {key} = {value}")
        else:
            print("❌ Use: /remember key = value")

    #to get the stored memory
    elif question.lower() == "/memory":

       if memory:
          print("\n========== 🧠 MEMORY ==========")

          for key, value in memory.items():
            print(f"{key}: {value}")

          print("===============================")

       else:
        print("🧠 Memory is empty.")

    #it is for to clear our stored memory
    elif question.lower().startswith("/forget"):
        key = question[8:].strip()

        if key in memory:
            del memory[key]

            with open(MEMORY_FILE, "w") as file:
                json.dump(memory,file,indent =4)

            print(f"🗑️ Forgot: {key}")

        else:
            print(f"❌ I don't have '{key}' in memory.")


    #helpbox command
    elif question.lower() == "/help":
        print("""
        Available Commands:

     /help       → Show this help menu
     /clear      → Clear conversation
     /history    → Show conversation history
     /remember   → Save something to memory
     /memory     → Show saved memories
     /forget     → Delete a saved memory 
     /exit       → Exit the chatbot
     
     """)

        
     #clear command
    elif question.lower() == "/clear":
        

        history.clear()

        with open(HISTORY_FILE,"w") as file:
            json.dump(history,file,indent = 4)

        chat = create_chat_with_history()

        print("👍Conversation Cleared!")


    elif question.lower() == "/history":
          

          print("\n========== CHAT HISTORY ==========\n")

          if len(history) == 0:
               print("No Conversation Yet!")

          else:
               for msg in history:
                   print(msg["role"] + ":", msg["text"])
                   print()

          print("======================\n") 


    
    else:
        try:

             memory_context = get_memory_context()

             if memory_context:
                 prompt = memory_context+ "\nUser question:\n" + question

             else:
                 prompt = question

             response = chat.send_message(prompt)

             answer = response.text.strip()


             print("\nGemini:", answer)

             history.append({
             "role": "You",
             "text": question
             })

             history.append({
             "role": "Gemini",
             "text": answer
             })

             with open(HISTORY_FILE, "w") as file:
              json.dump(history, file, indent=4)

             

        except Exception as e:

             if "503" in str(e):
                 print("⚠️ Gemini is currently busy. Please try again.")

             elif "429" in str(e):
                 print("⚠️ Gemini API quota exceeded. Please try again later.")

             else:
                 print("❌ Something went wrong.")
                 print("Error:",(e))