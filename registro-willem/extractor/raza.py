"""
Raza / etnia más probable a partir del nombre del paciente.

Se usa SOLO en el Mac, al leer el PDF original (fase 1): es el único momento en que se conoce el
nombre. Al informe anonimizado no pasa el nombre, solo la opción propuesta y el motivo, y en el
registro la propuesta queda pendiente de que una persona la confirme.

Es una aproximación por listas de nombres y apellidos frecuentes: acierta en lo evidente y, si no
reconoce nada, propone el valor por defecto acordado con el equipo («Hispana / latina»).
"""
import re
import unicodedata

POR_DEFECTO = "racial_group_hispanic"

# Origen que sugiere el nombre -> (opción del CRF, texto del motivo). El texto NUNCA incluye el nombre.
# El CRF no tiene la opción «Árabe»: se propone «Caucásica» (en las clasificaciones habituales, Oriente
# Medio y el norte de África se agrupan ahí). Si el equipo prefiere otra, basta con cambiarla aquí.
ORIGENES = {
    "arabe": ("racial_group_caucasian", "El nombre sugiere origen árabe o magrebí. El formulario no tiene la opción «Árabe»: se propone Caucásica"),
    "subsahariano": ("racial_group_african_race", "El nombre sugiere origen de África subsahariana"),
    "asia_oriental": ("racial_group_asian_race", "El nombre sugiere origen de Asia oriental"),
    "asia_sur": ("racial_group_asian_race", "El nombre sugiere origen del sur de Asia"),
    "europa_este": ("racial_group_caucasian", "El nombre sugiere origen de Europa del este"),
    "europa_norte": ("racial_group_caucasian", "El nombre sugiere origen del norte o centro de Europa"),
}

NOMBRES = {
    "subsahariano": """MAMADOU AMADOU OUSMANE IBRAHIMA ABDOULAYE MODOU CHEIKH SERIGNE BABACAR ALIOUNE PAPE MOUSTAPHA BOUBACAR SEKOU LAMINE
        FATOU FATOUMATA AMINATA MARIAMA AISSATOU ADAMA AWA KADIATOU BINTOU OUMOU KWAME KOFI CHINEDU EMEKA CHUKWUDI OLUWASEUN NGOZI""",
    "arabe": """MOHAMED MOHAMMED MOHAMAD MOHAMMAD MUHAMMAD MUHAMAD MOHAND MHAMED AHMED AHMAD HAMID HAMED HASSAN HASAN HUSSEIN HOUSSEIN HOUCINE
        YOUSSEF YOUSEF YUSUF IBRAHIM BRAHIM ISMAIL MUSTAFA MUSTAPHA MOSTAFA ABDELKADER ABDELAZIZ ABDERRAHIM ABDERRAHMAN ABDERRAHMANE ABDELLAH
        ABDALLAH ABDULLAH ABDELKRIM ABDELHAK ABDELMAJID ABDESLAM ABDESELAM ABDELILAH ABDELHAMID ABDELOUAHED KHALID JALID RACHID RASHID KARIM
        HICHAM HISHAM SOUFIANE SUFIAN BILAL HAMZA AYOUB ZAKARIA YASSINE YASIN NABIL TARIK TAREK MOUNIR MUNIR JAMAL DJAMEL LAHCEN LAHSEN DRISS
        IDRIS AZIZ NOUREDDINE REDOUANE SALAH MILOUD MIMOUN MIMUN BOUJEMAA LARBI LAARBI MOULAY TAHAR TAIEB KAMAL OTHMAN OTMAN ANOUAR ANWAR
        FATIHA FATNA KHADIJA JADIYA AICHA AISHA ZAHRA ZOHRA NAIMA LATIFA MALIKA HANAN HANANE SOUAD RACHIDA HAFIDA HABIBA SAIDA YAMINA RAHMA
        MBARKA HAYAT IKRAM IMANE HOUDA SANAA NAJAT ZINEB ZAINAB MERYEM LOUBNA WAFA KARIMA JAMILA NOURA HASNA SIHAM BOUCHRA GHIZLANE FATIMA-ZAHRA""",
    "asia_sur": "SINGH KAUR KUMAR RAJESH SURESH RAMESH SANJAY PRAKASH DEEPAK ANIL SUNIL GURPREET HARPREET MANPREET JASWINDER BALJIT",
    "asia_oriental": "WEI JUN MING HUI XIAOMING XIAOLI JIANHUA GUOQIANG LIPING YING HONG MEI",
    "europa_este": """VASILE GHEORGHE IOAN IOANA MIHAI MIHAELA ANDREI COSTEL DUMITRU NICOLAE VIOREL FLORIN MARIUS LIVIU SORIN ILIE PETRU STEFANIA
        SVETLANA OLEKSANDR VOLODYMYR OKSANA NATALIYA YURIY SERGIY IRYNA TETIANA LYUDMYLA VASYL MYKOLA DMITRI DMITRY VLADIMIR IGOR OLGA TATIANA
        GALINA NADEZHDA BOGDAN ZBIGNIEW KRZYSZTOF WOJCIECH AGNIESZKA MALGORZATA DRAGAN ZORAN GORAN MILAN STOYAN GEORGI DIMITAR""",
    "europa_norte": """JOHN WILLIAM JAMES MICHAEL RICHARD PETER BRIAN KEITH TREVOR GRAHAM NIGEL COLIN DEREK STUART MALCOLM KENNETH GEOFFREY
        MARGARET ELIZABETH SUSAN DOROTHY JEAN JOAN SHIRLEY MAUREEN BRENDA PAULINE HANS KLAUS HELGA JURGEN WOLFGANG HEINZ GUNTER HORST DIETER
        INGRID URSULA GERTRUD HELMUT MANFRED UWE JENS LARS SVEN ERIK ANDERS BJORN INGE ASTRID PIETER JAN WILLEM HENDRIK JOHANNES CORNELIS""",
}
APELLIDOS = {
    "subsahariano": """DIALLO DIOP NDIAYE TRAORE KEITA COULIBALY KONATE KONE SOW SARR GUEYE MBAYE NIANG CISSE TOURE DIARRA SYLLA BALDE JALLOW
        CEESAY DRAMMEH SANOGO DEMBELE SIDIBE KANTE CAMARA-SOW BARRY THIAM SECK SENE FAYE NDOYE DIENG DIOUF MBENGUE OKAFOR OKEKE ADEYEMI NWOSU
        MENSAH OSEI BOATENG OWUSU ASANTE ADJEI OKONKWO OBI EZE""",
    "arabe": """BENALI BOUZID BELHADJ CHAOUI IDRISSI ALAOUI AMRANI TAHIRI BENNANI FASSI CHERKAOUI LAHLOU BERRADA TAZI OUAZZANI HADDAD HAMDAOUI
        BOUKHARI BOUZIANE BELKACEM BENAISSA BENSAID BENSALAH MANSOURI NACIRI KADIRI FILALI ZEROUAL AZZOUZI EZZAHRAOUI ESSAIDI ERRAHMANI
        MOHAMED MOHAMMED AHMED HAMED ABDESELAM ABDELKADER MIMUN MIMOUN AMAR MOHAND HOSSAIN ABDELLAOUI BOUTAHAR CHAIB DAOUDI HAMMOUCHI JABRI
        KHALDI LAMRANI MOUSSAOUI RAHMOUNI SAIDI YAHYAOUI ZIANI ZOUHAIR OUALI OUCHEN OULAD""",
    "asia_sur": "SINGH KAUR KUMAR PATEL SHARMA KHAN BEGUM HUSSAIN AKHTAR CHAUDHRY CHAUDHARY IQBAL MIAH UDDIN SHAH GUPTA REDDY NAIR MALIK BUTT",
    "asia_oriental": """CHEN WANG ZHANG LIU YANG HUANG ZHAO ZHOU XU ZHU GUO ZHENG XIE JIANG WONG CHAN CHEUNG NGUYEN TRAN PHAM KIM PARK CHOI
        TANAKA SUZUKI SATO WATANABE YAMAMOTO NAKAMURA""",
    "europa_norte": """SMITH JONES BROWN TAYLOR WILSON WILLIAMS JOHNSON DAVIES EVANS ROBERTS WALKER WRIGHT THOMPSON ROBINSON HUGHES EDWARDS
        TURNER HARRISON COOPER BAKER CLARKE CLARK JACKSON HARRIS WATSON MULLER SCHMIDT SCHNEIDER FISCHER WEBER MEYER WAGNER BECKER HOFFMANN
        SCHULZ KOCH BAUER RICHTER KLEIN JANSEN JANSSEN ANDERSSON JOHANSSON KARLSSON NILSSON NIELSEN HANSEN JENSEN PEDERSEN LARSEN OLSEN""",
}
# Partículas con las que empiezan muchos apellidos árabes o magrebíes («El Amrani», «Ben Ali», «Ait Ouali»)
PARTICULAS_ARABES = {"EL", "AL", "BEN", "BIN", "ABU", "ABOU", "AIT", "OULD", "BOU", "BENT"}
TERMINACIONES_ESTE = ("ESCU", "OVIC", "EVIC", "ENKO", "CHUK", "CZYK", "OWSKI", "EWSKI", "OWSKA", "EWSKA", "ISHVILI", "IDZE")

_N = {k: set(v.split()) for k, v in NOMBRES.items()}
_A = {k: set(v.split()) for k, v in APELLIDOS.items()}
ORDEN = ["subsahariano", "arabe", "asia_sur", "asia_oriental", "europa_este", "europa_norte"]


def _normal(s):
    s = unicodedata.normalize("NFD", str(s or "").upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z\- ']", " ", s).strip()


def _origen(nombre, apellido1, apellido2):
    nom = [t for t in _normal(nombre).split() if t]
    aps = [_normal(apellido1), _normal(apellido2)]
    tokens_ap = [t for a in aps for t in a.split() if t]
    # 1) apellidos: son la pista más fiable
    for a in aps:
        partes = a.split()
        if len(partes) >= 2 and partes[0] in PARTICULAS_ARABES:
            return "arabe"
    for o in ORDEN:
        if o in _A and any(t in _A[o] for t in tokens_ap):
            return o
    if any(t.endswith(TERMINACIONES_ESTE) and len(t) > 5 for t in tokens_ap):
        return "europa_este"
    # 2) nombre de pila
    for o in ORDEN:
        if any(t in _N[o] for t in nom) or "-".join(nom) in _N[o]:
            return o
    return None


def inferir(nombre, apellido1="", apellido2=""):
    """-> {"codigo": opción del CRF, "motivo": texto sin el nombre, "por_defecto": bool}"""
    o = _origen(nombre, apellido1, apellido2)
    if not o:
        return {"codigo": POR_DEFECTO, "motivo": "Valor por defecto: el nombre no sugiere otro origen", "por_defecto": True}
    codigo, motivo = ORIGENES[o]
    return {"codigo": codigo, "motivo": motivo, "por_defecto": False}
