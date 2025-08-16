from typing import List, Dict

ILE_DE_FRANCE_CITIES = [
    "Paris", "Boulogne-Billancourt", "Saint-Denis", "Argenteuil", "Montreuil",
    "Nanterre", "Vitry-sur-Seine", "Créteil", "Asnières-sur-Seine", "Versailles",
    "Colombes", "Aubervilliers", "Aulnay-sous-Bois", "Courbevoie", "Rueil-Malmaison",
    "Champigny-sur-Marne", "Saint-Maur-des-Fossés", "Drancy", "Issy-les-Moulineaux",
    "Noisy-le-Grand", "Levallois-Perret", "Cergy", "Antony", "Neuilly-sur-Seine",
    "Clichy", "Ivry-sur-Seine", "Sarcelles", "Villejuif", "Le Blanc-Mesnil", "Pantin",
    "Maisons-Alfort", "Épinay-sur-Seine", "Évry-Courcouronnes", "Chelles", "Meaux",
    "Fontenay-sous-Bois", "Bondy", "Clamart", "Sartrouville", "Bobigny", "Sevran",
    "Corbeil-Essonnes", "Vincennes", "Montrouge", "Suresnes", "Saint-Ouen-sur-Seine",
    "Massy", "Meudon", "Puteaux", "Mantes-la-Jolie", "Rosny-sous-Bois", "Gennevilliers",
    "Livry-Gargan", "Alfortville", "Choisy-le-Roi", "Noisy-le-Sec", "Garges-lès-Gonesse",
    "La Courneuve", "Saint-Germain-en-Laye", "Melun", "Gagny", "Stains", "Bagneux",
    "Pontault-Combault", "Châtillon", "Poissy", "Villepinte", "Savigny-sur-Orge",
    "Bagnolet", "Sainte-Geneviève-des-Bois", "Tremblay-en-France", "Conflans-Sainte-Honorine",
    "Franconville", "Neuilly-sur-Marne", "Le Perreux-sur-Marne", "Châtenay-Malabry",
    "Montigny-le-Bretonneux", "Palaiseau", "Athis-Mons", "Villeneuve-Saint-Georges",
    "Trappes", "Les Mureaux", "Houilles", "Plaisir", "Nogent-sur-Marne", "Chatou",
    "Goussainville", "Viry-Châtillon", "L'Haÿ-les-Roses", "Vigneux-sur-Seine",
    "Charenton-le-Pont", "Pontoise", "Cachan", "Savigny-le-Temple", "Clichy-sous-Bois",
    "Malakoff", "Villemomble", "La Garenne-Colombes", "Saint-Cloud", "Draveil",
    "Le Plessis-Robinson", "Thiais", "Yerres", "Ermont", "Bezons", "Le Chesnay-Rocquencourt",
    "Villiers-sur-Marne", "Grigny", "Herblay-sur-Seine", "Bois-Colombes", "Vanves",
    "Guyancourt", "Ris-Orangis", "Villiers-le-Bel", "Fresnes", "Sannois",
    "Bussy-Saint-Georges", "Sucy-en-Brie", "Villeparisis", "Brétigny-sur-Orge",
    "Gonesse", "Brunoy", "Taverny", "Romainville", "Montfermeil", "Le Kremlin-Bicêtre",
    "Limeil-Brévannes", "Élancourt", "Rambouillet", "Champs-sur-Marne", "Les Ulis",
    "Eaubonne", "Saint-Ouen-l'Aumône", "Villeneuve-la-Garenne", "Étampes",
    "Fontenay-aux-Roses", "Montgeron", "Cormeilles-en-Parisis", "Torcy",
    "Maisons-Laffitte", "Les Pavillons-sous-Bois", "Sèvres", "Orly", "Roissy-en-Brie",
    "Les Lilas", "Saint-Mandé", "Combs-la-Ville", "Deuil-la-Barre", "Longjumeau",
    "Dammarie-les-Lys"
]


GENEVA_CITIES = [
    "Avully", "Avusy", "Bardonnex", "Bellevue", "Bernex", "Carouge",
    "Cartigny", "Céligny", "Chancy", "Chêne-Bougeries", "Chêne-Bourg",
    "Choulex", "Collex-Bossy", "Collonge-Bellerive", "Cologny",
    "Confignon", "Corsier", "Dardagny", "Genève", "Genthod",
    "Le Grand-Saconnex", "Gy", "Hermance", "Jussy", "Lancy",
    "Meinier", "Meyrin", "Onex", "Perly-Certoux", "Plan-les-Ouates",
    "Pregny-Chambésy", "Presinge", "Puplinge", "Russin", "Satigny",
    "Soral", "Thônex", "Troinex", "Vandoeuvres", "Vernier",
    "Versoix", "Veyrier", "Anières"
]


LOCATION_PRESETS = {
    "idf": ILE_DE_FRANCE_CITIES,
    "geneva": GENEVA_CITIES,
}

PRESET_COUNTRIES = {
    "idf": ["FR"],
    "geneva": ["CH"],
}
