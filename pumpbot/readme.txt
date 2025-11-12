🧠 Kurulum Talimatı

Raspberry Pi üzerinde:

curl -sSL https://yourdomain.com/install_pumpgpt.sh | bash


veya dosyayı manuel koyup:

chmod +x install_pumpgpt.sh
./install_pumpgpt.sh


Sonra .env içindeki bot token’ını, API keylerini ve chat ID’lerini düzenle.
Servis zaten aktif hale gelir. Yeniden başlatmak veya log izlemek için:

sudo systemctl restart pumpgpt
sudo journalctl -u pumpgpt -f