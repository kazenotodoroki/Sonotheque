SONOTHÈQUE — gestionnaire de banques de sons (sound design)
============================================================

INSTALLATION (Windows 10 / 11)
1. Installez Python 3.10 ou plus récent : https://www.python.org/downloads/
   -> cochez « Add python.exe to PATH » pendant l'installation.
2. Double-cliquez sur « Lancer Sonotheque.bat ».
   La première fois, il installe ce qu'il faut (1–2 min). Ensuite l'app s'ouvre directement.
3. (Optionnel) « Creer l executable.bat » fabrique un vrai Sonotheque.exe autonome
   dans dist\Sonotheque\ — pratique pour l'épingler à la barre des tâches.

MISE À JOUR depuis une version précédente
Remplacez les fichiers du dossier (gardez le sous-dossier .venv). Votre index est conservé ;
les formes d'onde déjà calculées sont recalculées au nouveau format (plus compact).

UTILISATION
- « + » à côté de BIBLIOTHÈQUES : choisissez le dossier d'une banque (ex. BOOM One).
  Le scan tourne en arrière-plan ; vous pouvez travailler pendant ce temps (× pour l'arrêter).
- Clic droit sur une bibliothèque : renommer, rescanner, calculer les formes d'onde,
  exporter l'index, ouvrir le dossier, retirer.
- Catégories / sous-catégories : lues dans les métadonnées iXML (Soundminer/UCS),
  sinon dans le nom de fichier UCS (ex. ANMLInsc_...), sinon dans les dossiers.
- Panneau INFOS à droite : description complète, mots-clés (cliquer = ajouter à la recherche),
  détails techniques, chemin. Redimensionnable en tirant sur son bord gauche ; Ctrl+I le masque.
- Clic droit sur l'en-tête du tableau : afficher / masquer des colonnes (Description, Bits, Format…).

RECHERCHE
- Plusieurs mots : TOUS doivent correspondre (Fly Insect Movement).
- Entrée (ou virgule) transforme le texte en tag. Retour arrière retire le dernier tag.
- -mot exclut (ex. insect -bee). "door slam" entre guillemets = expression.
- Porte sur nom, nom de fichier, description, mots-clés, catégorie, sous-catégorie,
  source et dossiers. Accents ignorés.
- Filtre Tous / Mono / Stéréo / Multi en haut. « Mono » est surligné en orange.

LECTURE
- Lecture auto à la sélection (désactivable). Espace = lecture/pause,
  Entrée = depuis le début, ← → = ±1 s, clic sur la forme d'onde = aller à.

REAPER
- Bouton « Reaper » (Ctrl+R) : insère la sélection dans le projet ouvert,
  AU CURSEUR D'ÉDITION, SUR LA PISTE SÉLECTIONNÉE (plusieurs sons = enchaînés).
  Une seule annulation (Ctrl+Z dans Reaper) retire l'insertion.
- La première fois, la Sonothèque propose d'installer un petit script dans Reaper
  (Scripts\Sonotheque + une ligne dans Scripts\__startup.lua, sans toucher au reste).
  Si Reaper était ouvert à ce moment-là, fermez-le et rouvrez-le UNE fois.
  Si Reaper est fermé, le bouton l'ouvre puis insère les sons.
- Installation portable de Reaper : Réglages › Dossier de ressources Reaper…
- Glisser-déposer une ou plusieurs lignes dans Reaper fonctionne aussi.

EXPLORATEUR
- Bouton « Explorateur » (Ctrl+E) : ouvre le dossier avec le fichier sélectionné.

UTILISER UNE BIBLIOTHÈQUE SUR UN AUTRE PC (sans rescanner)
1. Sur le PC où elle est analysée : clic droit sur la bibliothèque ›
   « Exporter l'index dans le dossier » (ou Réglages › Exporter les index de toutes les bibliothèques).
   Un fichier Sonotheque.sonolib est créé à la racine du dossier de sons.
2. Copiez / déplacez le dossier de sons (disque externe, NAS, autre lettre de lecteur : peu importe).
3. Sur l'autre PC : « + » et choisissez le dossier. L'index est détecté : tous les sons
   apparaissent en quelques secondes / minutes, sans relire les fichiers audio.
   Seuls les fichiers ajoutés ou modifiés depuis l'export sont analysés.
   Si le dossier est en lecture seule : « Exporter l'index vers… » puis, sur l'autre PC,
   Réglages › Importer un index (.sonolib)… et indiquez où est le dossier.

FORMES D'ONDE
- Calculées à la première écoute, ou toutes d'un coup : clic droit › Calculer les formes d'onde
  (tâche de fond, reprend où elle s'était arrêtée).
- Format compact : environ 0,3 à 0,6 Ko par son, soit ~150–300 Mo pour 500 000 sons.
  À l'export, une case permet de les inclure ou non.

DONNÉES
L'index est stocké dans %APPDATA%\Sonotheque\Sonotheque\library.db
Vos fichiers audio ne sont jamais modifiés.
