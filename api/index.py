from fastapi import FastAPI
app = FastAPI()
@pp.get("/")
def home():
  return {"pesan": "Koleksi Fauna UGM Berhasil Jalan!"}
