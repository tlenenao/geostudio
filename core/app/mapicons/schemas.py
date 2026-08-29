# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel

# Une seule définition, importée par routes.py — jamais dupliquée.
# PNG et SVG (D4). Un SVG est ASSAINI à l'écriture par app.mapicons.svg et
# c'est la version assainie qui est stockée : la lecture ne réassainit pas.
ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/svg+xml"})

# Plafond DUR appliqué pendant la lecture du corps, morceau par morceau : dès
# dépassement la route abandonne et répond 413, sans jamais tenir le fichier
# entier en mémoire (D7).
#
# Justification de la valeur : un pictogramme Lucide fait 300-600 octets, un
# logo SVG détaillé quelques dizaines de kilo-octets, un PNG 256x256 opaque
# ~100 Ko. 200 Ko laisse une marge large tout en bornant le travail
# d'assainissement (un parse XML), et c'est la MÊME valeur que
# _MAX_SANITIZED_BYTES dans svg.py : une seule borne à retenir.
MAX_ICON_BYTES = 200_000
UPLOAD_CHUNK_BYTES = 64 * 1024

# Bornes des deux champs texte, valeur reprise du précédent
# app/tileset3d/schemas.py:5-7 (Field(min_length=1, max_length=255)). Ici elles
# ne peuvent PAS être portées par un modèle pydantic : `title` et `category`
# arrivent en champs de formulaire multipart, pas dans un corps JSON. La route
# les applique, et cette constante est leur unique définition.
MAX_TEXT_FIELD_CHARS = 255

# La signature PNG et la détection de type vivent dans svg.py
# (sniff_content_type) : une seule définition, à côté de l'assainisseur.

# PAS de MapIconPresignRequest ni de MapIconPresignResponse : D7 (déviation 16)
# supprime la présignation sur cette surface. PAS de MapIconCreate non plus —
# `title` et `category` arrivent en champs de formulaire multipart, validés par
# la route, et un modèle pydantic ne se mélange pas à un corps multipart.


class MapIconOut(BaseModel):
    # Modèle de SORTIE uniquement : aucune contrainte de longueur ici, sinon
    # une ligne déjà en base hors bornes ferait échouer la sérialisation. Les
    # bornes sont appliquées à l'ENTRÉE, par la route.
    id: str
    title: str
    category: str
    contentType: str
    createdAt: str
