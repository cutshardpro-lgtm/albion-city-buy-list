@echo off
rem City Buy List - serveur local etape 0
rem Sert ce dossier sur http://localhost:8000 (la page ne doit JAMAIS etre ouverte en file://,
rem le client albiondata rejette l'Origin "null").
cd /d "%~dp0"
echo Serveur local demarre : http://localhost:8000/test_ws.html
echo Laisser cette fenetre ouverte. Ctrl+C pour arreter.
python -m http.server 8000
