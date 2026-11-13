"""
Genera el DICCIONARIO MAESTRO del registro WILLEM a partir de la hoja
"Data Dictionary" del CRF original (WILLEM_Registry_CRF.xlsx).

Uso:
    python3 generar_diccionario.py RUTA_AL_CRF.xlsx  SALIDA.xlsx  [PROPUESTA_AGRUPACION.xlsx]

El diccionario maestro es la "fuente de la verdad" de la aplicación:
cada fila es un campo del formulario, con su traducción al español,
qué patologías lo usan, cuándo se muestra y cómo se exporta.

Una vez revisado por el equipo clínico, se edita directamente el Excel
de salida (no hace falta volver a ejecutar este script).
"""
import re
import sys
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Grupos de patología (etiquetas)
#   COMUN : se muestra a todos los pacientes
#   IC    : insuficiencia cardiaca            (heart_failure = 1)
#   ISQ   : cardiopatía isquémica / infarto   (ischemic_cardiomyopathy = 1 o myocardial_infarction = 1)
#   EAO   : estenosis aórtica                 (aortic_stenosis = 1)
#   MCH   : miocardiopatía hipertrófica       (hypertrophic_cardiomyopathy = 1)
#   ATTR  : amiloidosis cardiaca por TTR      (amyloidosis_attr = 1)
#   QTL   : síndrome de QT largo              (long_qt_syndrome = 1)
# ---------------------------------------------------------------------------
GRUPOS = {
    "COMUN": "Todos los pacientes",
    "ISQ": "Cardiopatía isquémica (ischemic_cardiomyopathy = 1)",
    "IC": "Insuficiencia cardiaca (heart_failure = 1)",
    "EAO": "Estenosis aórtica (aortic_stenosis = 1)",
    "MCH": "Miocardiopatía hipertrófica (hypertrophic_cardiomyopathy = 1)",
    "QTL": "Síndrome de QT largo (long_qt_syndrome = 1)",
    "ATTR": "Amiloidosis cardiaca por transtiretina (amyloidosis_attr = 1)",
    "IAM": "Infarto de miocardio (myocardial_infarction = 1)",
    "HTA": "Cardiopatía hipertensiva (hypertensive_disease = 1)",
    "OTRO": "Otros (other_disease)",
}

# ---------------------------------------------------------------------------
# Traducción y reglas por fila de la hoja "Data Dictionary".
# fila: (codigo_si_falta, texto_es, ayuda_es, grupos, mostrar_si, min, max)
#   codigo_si_falta: solo se usa si el CRF no trae código (se marca PROVISIONAL)
# ---------------------------------------------------------------------------
C = "COMUN"
T = {
    # 0. Metadatos
    4: (None, "Fecha y hora de registro", "Se rellena automáticamente al crear el caso.", C, "", None, None),
    5: (None, "Identificador del centro", "Fijo: ARRIXACA.", C, "", None, None),
    6: (None, "Número de caso (seudonimizado)", "Número del caso asignado por el data manager. NUNCA el CIP, NHC ni nombre.", C, "", None, None),
    7: (None, "Tipo de reclutamiento", "", C, "", None, None),
    8: (None, "Retrospectivo", "", C, "", None, None),
    9: (None, "Prospectivo", "", C, "", None, None),
    10: (None, "Criterios de elegibilidad", "Marcar todos los que se cumplen.", C, "", None, None),
    11: (None, "Edad cumple criterio de inclusión", "", C, "", None, None),
    12: (None, "ECG disponible", "", C, "", None, None),
    13: (None, "Cardiopatía diagnosticada", "", C, "", None, None),
    14: (None, "Consentimiento informado firmado", "", C, "", None, None),
    15: (None, "Ámbito asistencial", "", C, "", None, None),
    16: (None, "Hospitalizado", "", C, "", None, None),
    17: (None, "Ambulatorio / consultas", "", C, "", None, None),
    18: (None, "Urgencias", "", C, "", None, None),
    19: (None, "Desconocido", "", C, "", None, None),
    # 1. Demografía
    21: (None, "Fecha de nacimiento", "", C, "", None, None),
    22: (None, "Sexo biológico", "", C, "", None, None),
    23: (None, "Varón", "", C, "", None, None),
    24: (None, "Mujer", "", C, "", None, None),
    25: (None, "Talla (cm)", "En el momento del ECG.", C, "", 100, 230),
    26: (None, "Peso (kg)", "En el momento del ECG.", C, "", 25, 250),
    27: (None, "Raza / etnia", "Elegir una sola opción.", C, "", None, None),
    28: (None, "Africana", "", C, "", None, None),
    29: (None, "Indígena americana", "", C, "", None, None),
    30: (None, "Asiática", "", C, "", None, None),
    31: (None, "Caucásica", "", C, "", None, None),
    32: (None, "Hispana / latina", "", C, "", None, None),
    33: (None, "Isleña del Pacífico", "", C, "", None, None),
    34: (None, "Mixta", "", C, "", None, None),
    35: (None, "Desconocida", "", C, "", None, None),
    36: (None, "Tabaquismo", "", C, "", None, None),
    37: (None, "Fumador activo", "", C, "", None, None),
    38: (None, "Exfumador", "", C, "", None, None),
    39: (None, "No fumador", "", C, "", None, None),
    40: (None, "Consumo de alcohol (UBE/semana)", "Unidades de bebida estándar por semana.", C, "", 0, 100),
    41: (None, "Actividad física moderada-intensa (h/semana)", "", C, "", 0, 60),
    # 2. Diagnóstico
    43: (None, "Cardiopatía isquémica", "", C, "", None, None),
    44: (None, "Fecha diagnóstico cardiopatía isquémica", "", "ISQ", "ischemic_cardiomyopathy = 1", None, None),
    45: (None, "Cardiopatía hipertensiva", "", C, "", None, None),
    46: (None, "Fecha diagnóstico cardiopatía hipertensiva", "", C, "hypertensive_disease = 1", None, None),
    47: (None, "Insuficiencia cardiaca", "", C, "", None, None),
    48: (None, "Fecha diagnóstico insuficiencia cardiaca", "", "IC", "heart_failure = 1", None, None),
    49: (None, "Tipo de insuficiencia cardiaca", "", "IC", "heart_failure = 1", None, None),
    50: (None, "Disfunción ventricular izquierda (sin especificar)", "", "IC", "heart_failure = 1", None, None),
    51: (None, "IC con FEVI reducida (≤40 %)", "", "IC", "heart_failure = 1", None, None),
    52: (None, "IC con FEVI levemente reducida (41–49 %)", "", "IC", "heart_failure = 1", None, None),
    53: (None, "IC con FEVI preservada (≥50 %)", "", "IC", "heart_failure = 1", None, None),
    54: (None, "Otro tipo de insuficiencia cardiaca (especificar)", "", "IC", "heart_failure = 1", None, None),
    55: (None, "Infarto agudo de miocardio", "", C, "", None, None),
    56: (None, "Fecha del infarto", "", "ISQ", "myocardial_infarction = 1", None, None),
    57: (None, "Clasificación del IAM por ECG", "", "ISQ", "myocardial_infarction = 1", None, None),
    58: (None, "IAMCEST (con elevación del ST)", "", "ISQ", "myocardial_infarction = 1", None, None),
    59: (None, "IAMSEST (sin elevación del ST)", "", "ISQ", "myocardial_infarction = 1", None, None),
    60: (None, "Clasificación del IAM por oclusión", "", "ISQ", "myocardial_infarction = 1", None, None),
    61: (None, "IAM oclusivo (OMI)", "", "ISQ", "myocardial_infarction = 1", None, None),
    62: (None, "IAM no oclusivo (NOMI)", "", "ISQ", "myocardial_infarction = 1", None, None),
    63: (None, "Estenosis aórtica", "", C, "", None, None),
    64: (None, "Fecha diagnóstico estenosis aórtica", "", "EAO", "aortic_stenosis = 1", None, None),
    65: (None, "Gravedad de la estenosis aórtica", "", "EAO", "aortic_stenosis = 1", None, None),
    66: (None, "Leve", "", "EAO", "aortic_stenosis = 1", None, None),
    67: (None, "Moderada", "", "EAO", "aortic_stenosis = 1", None, None),
    68: (None, "Grave", "", "EAO", "aortic_stenosis = 1", None, None),
    69: (None, "Miocardiopatía hipertrófica", "", C, "", None, None),
    70: (None, "Fecha diagnóstico miocardiopatía hipertrófica", "", "MCH", "hypertrophic_cardiomyopathy = 1", None, None),
    71: (None, "Tipo de miocardiopatía hipertrófica", "", "MCH", "hypertrophic_cardiomyopathy = 1", None, None),
    72: (None, "Obstructiva", "", "MCH", "hypertrophic_cardiomyopathy = 1", None, None),
    73: (None, "No obstructiva", "", "MCH", "hypertrophic_cardiomyopathy = 1", None, None),
    74: (None, "Síndrome de QT largo", "", C, "", None, None),
    75: (None, "Fecha diagnóstico QT largo", "", "QTL", "long_qt_syndrome = 1", None, None),
    76: (None, "Amiloidosis cardiaca por transtiretina (ATTR)", "", C, "", None, None),
    77: (None, "Fecha diagnóstico amiloidosis ATTR", "", "ATTR", "amyloidosis_attr = 1", None, None),
    78: (None, "Subtipo de amiloidosis ATTR", "", "ATTR", "amyloidosis_attr = 1", None, None),
    79: (None, "ATTR variante / hereditaria (ATTRv)", "", "ATTR", "amyloidosis_attr = 1", None, None),
    80: (None, "ATTR nativa / wild type (ATTRwt)", "", "ATTR", "amyloidosis_attr = 1", None, None),
    81: (None, "Otro diagnóstico (especificar, con fecha)", "Texto libre; si es posible incluir código CIE-11.", C, "", None, None),
    83: ("amyloidosis_attr_mgus", "Gammapatía monoclonal de significado incierto (GMSI)", "", "ATTR", "amyloidosis_attr = 1", None, None),
    84: ("ecg_low_voltage", "Bajo voltaje en ECG", "QRS <1 mV en TODAS las precordiales o <0,5 mV en TODAS las de miembros.", "ATTR", "amyloidosis_attr = 1", None, None),
    86: ("mi_number_of_stents", "Número de stents implantados", "", "ISQ", "myocardial_infarction = 1", 0, 20),
    87: ("mi_cardiopulmonary_resuscitation", "Necesidad de RCP", "", "ISQ", "myocardial_infarction = 1", None, None),
    88: ("mi_mechanical_circulatory_support", "Necesidad de soporte circulatorio mecánico", "", "ISQ", "myocardial_infarction = 1", None, None),
    89: ("conduction_abnormality", "Trastornos de la conducción", "Puede marcar varios.", "ISQ ATTR", "", None, None),
    90: ("conduction_abnormality_none", "Ninguno", "", "ISQ ATTR", "", None, None),
    91: ("conduction_abnormality_sick_sinus", "Enfermedad del nodo sinusal", "", "ISQ ATTR", "", None, None),
    92: ("conduction_abnormality_rbbb", "Bloqueo de rama derecha (BRD)", "", "ISQ ATTR", "", None, None),
    93: ("conduction_abnormality_lbbb", "Bloqueo de rama izquierda (BRI)", "", "ISQ ATTR", "", None, None),
    94: ("conduction_abnormality_av_block", "Bloqueo AV", "", "ISQ ATTR", "", None, None),
    95: ("conduction_abnormality_other", "Otro", "", "ISQ ATTR", "", None, None),
    96: ("coronary_revascularization", "Tipo de revascularización coronaria", "Puede marcar varios.", "ISQ", "", None, None),
    97: ("coronary_revascularization_pci", "Intervencionismo coronario percutáneo (ICP)", "", "ISQ", "", None, None),
    98: ("coronary_revascularization_cabg", "Cirugía de revascularización (bypass)", "", "ISQ", "", None, None),
    # 3. Pruebas diagnósticas
    100: (None, "Fecha del ecocardiograma (basal)", "Solo el eco basal; no se recogen ecos evolutivos.", C, "", None, None),
    101: (None, "FEVI (%)", "", C, "", 5, 90),
    102: (None, "Diámetro telediastólico VI (DTDVI, mm)", "", C, "", 20, 100),
    103: (None, "Grosor septo interventricular en PLAX (mm)", "", "IC EAO MCH ATTR", "", 4, 40),
    104: (None, "Grosor pared posterior en PLAX (mm)", "", "IC EAO MCH ATTR", "", 4, 35),
    105: (None, "Grosor máximo de pared VI (mm)", "", "MCH ATTR EAO", "", 5, 50),
    106: (None, "Strain longitudinal global VI (%)", "Introducir con signo negativo (p. ej. -18).", "IC MCH ATTR", "", -35, 0),
    107: (None, "Área valvular aórtica (cm²)", "", "EAO", "", 0.2, 5),
    108: (None, "Velocidad pico aórtica, Vmax (m/s)", "", "EAO", "", 0.5, 7),
    109: (None, "Gradiente medio aórtico (mmHg)", "", "EAO", "", 0, 150),
    110: (None, "Fecha de la gammagrafía", "", "ATTR", "", None, None),
    111: (None, "Grado de Perugini", "", "ATTR", "", None, None),
    112: (None, "Grado 0", "", "ATTR", "", None, None),
    113: (None, "Grado 1", "", "ATTR", "", None, None),
    114: (None, "Grado 2", "", "ATTR", "", None, None),
    115: (None, "Grado 3", "", "ATTR", "", None, None),
    116: (None, "Fecha de la coronariografía", "", "ISQ", "", None, None),
    117: (None, "Dominancia coronaria", "", "ISQ", "", None, None),
    118: (None, "Derecha", "", "ISQ", "", None, None),
    119: (None, "Izquierda", "", "ISQ", "", None, None),
    120: (None, "Codominancia", "", "ISQ", "", None, None),
    121: (None, "Desconocida", "", "ISQ", "", None, None),
    122: (None, "Arteria ocluida", "Puede marcar varias.", "ISQ", "", None, None),
    123: (None, "Circunfleja (Cx)", "", "ISQ", "", None, None),
    124: (None, "Descendente anterior (DA)", "", "ISQ", "", None, None),
    125: (None, "Coronaria derecha (CD)", "", "ISQ", "", None, None),
    126: (None, "Otra", "", "ISQ", "", None, None),
    127: (None, "Flujo TIMI (fecha)", "", "ISQ", "", None, None),
    128: (None, "TIMI 0", "", "ISQ", "", None, None),
    129: (None, "TIMI 1", "", "ISQ", "", None, None),
    130: (None, "TIMI 2", "", "ISQ", "", None, None),
    131: (None, "TIMI 3", "", "ISQ", "", None, None),
    132: (None, "Fecha de la biopsia", "", "ATTR", "", None, None),
    133: (None, "Biopsia confirma amiloidosis", "", "ATTR", "", None, None),
    134: (None, "Fecha del estudio genético", "", "ATTR MCH", "", None, None),
    135: (None, "Estudio genético confirma amiloidosis ATTR", "", "ATTR", "", None, None),
    136: (None, "Estudio genético confirma MCH", "", "MCH", "", None, None),
    137: ("genetic_screening_hcm_result", "Resultado del estudio genético MCH (fecha)", "", "MCH", "", None, None),
    138: ("genetic_screening_hcm_result_negative", "Negativo", "", "MCH", "", None, None),
    139: ("genetic_screening_hcm_result_positive", "Positivo", "", "MCH", "", None, None),
    140: ("genetic_screening_hcm_result_uncertain", "Variante de significado incierto", "", "MCH", "", None, None),
    141: (None, "Fecha de la analítica", "", C, "", None, None),
    142: (None, "BNP (pg/mL)", "", C, "", 0, 50000),
    143: (None, "NT-proBNP (pg/mL)", "", C, "", 0, 100000),
    144: (None, "Troponina I ultrasensible (ng/L)", "", C, "", 0, 100000),
    145: (None, "Troponina T ultrasensible (ng/L)", "", C, "", 0, 100000),
    146: (None, "Creatinina (mg/dL)", "", C, "", 0.2, 20),
    147: (None, "Filtrado glomerular MDRD (mL/min/1,73 m²)", "", C, "", 2, 200),
    148: (None, "Fecha del ECG", "", C, "", None, None),
    # 4. Situación basal
    149: (None, "Fecha de la valoración basal", "", C, "", None, None),
    150: (None, "Embarazo actual", "", C, "biological_sex_female = 1", None, None),
    151: (None, "Presión arterial sistólica (mmHg)", "Si hay varias tomas, la media.", C, "", 50, 260),
    152: (None, "Presión arterial diastólica (mmHg)", "Si hay varias tomas, la media.", C, "", 20, 160),
    153: (None, "Frecuencia cardiaca en reposo (lpm)", "", C, "", 20, 250),
    # 5. Factores de riesgo
    155: (None, "Hipertensión arterial", "", C, "", None, None),
    156: ("hypertension_medication", "Tratamiento antihipertensivo", "", C, "hypertension = 1", None, None),
    157: (None, "Diabetes mellitus tipo 1", "", C, "", None, None),
    158: (None, "Diabetes mellitus tipo 2", "", C, "", None, None),
    159: (None, "Dislipemia", "", C, "", None, None),
    160: (None, "Obesidad diagnosticada", "", C, "", None, None),
    161: (None, "Antecedentes familiares de cardiopatía isquémica u otra enfermedad circulatoria", "", C, "", None, None),
    162: (None, "Antecedentes familiares de enfermedad coronaria precoz", "", C, "", None, None),
    # 6. Historia cardiovascular
    164: (None, "Clase funcional NYHA (fecha)", "", C, "", None, None),
    165: (None, "NYHA I", "", C, "", None, None),
    166: (None, "NYHA II", "", C, "", None, None),
    167: (None, "NYHA III", "", C, "", None, None),
    168: (None, "NYHA IV", "", C, "", None, None),
    169: (None, "Síncope previo", "", C, "", None, None),
    170: (None, "Síncope de causa no aclarada", "", C, "", None, None),
    171: (None, "Esperanza de vida estimada < 24 meses", "", C, "", None, None),
    172: ("arrhythmogenic_dysplasia", "Displasia arritmogénica", "", "QTL MCH", "", None, None),
    173: ("long_qt_syndrome_history", "Síndrome de QT largo (antecedente)", "DUPLICADO de long_qt_syndrome en Diagnóstico: revisar.", "QTL", "", None, None),
    174: ("brugada_syndrome", "Síndrome de Brugada", "", "QTL MCH", "", None, None),
    175: ("myocarditis", "Miocarditis", "", "QTL MCH", "", None, None),
    176: ("wpw_syndrome", "Síndrome de Wolff-Parkinson-White", "DUPLICADO de prior_wpw_preexcitation: revisar.", "QTL MCH", "", None, None),
    177: ("polymorphic_ventricular_tachycardia", "Taquicardia ventricular polimórfica", "DUPLICADO de prior_polymorphic_ventricular_tachycardia: revisar.", "QTL MCH", "", None, None),
    178: ("ventricular_fibrillation", "Fibrilación ventricular", "DUPLICADO de prior_ventricular_fibrillation: revisar.", "QTL MCH", "", None, None),
    179: ("family_history_hcm", "Antecedentes familiares de miocardiopatía hipertrófica", "", "MCH", "", None, None),
    # Eventos previos
    181: (None, "Síndrome coronario agudo previo", "", C, "", None, None),
    182: (None, "Ictus isquémico o AIT previo", "", C, "", None, None),
    183: (None, "Parada cardiaca por arritmia ventricular previa", "", C, "", None, None),
    184: (None, "Ingreso previo por descompensación de IC", "", C, "", None, None),
    185: (None, "Inestabilidad hemodinámica previa (inotrópicos/vasopresores o UCI)", "", C, "", None, None),
    186: (None, "Arritmias previas", "", C, "", None, None),
    187: (None, "Fibrilación auricular", "", C, "prior_arrhythmias = 1", None, None),
    188: (None, "Tipo de fibrilación auricular", "", C, "prior_atrial_fibrillation = 1", None, None),
    189: (None, "Paroxística", "", C, "prior_atrial_fibrillation = 1", None, None),
    190: (None, "Persistente", "", C, "prior_atrial_fibrillation = 1", None, None),
    191: (None, "Permanente", "", C, "prior_atrial_fibrillation = 1", None, None),
    192: (None, "Flutter auricular", "", C, "prior_arrhythmias = 1", None, None),
    193: (None, "Taquicardia ventricular sostenida", "", C, "prior_arrhythmias = 1", None, None),
    194: (None, "Taquicardia ventricular polimórfica", "", C, "prior_arrhythmias = 1", None, None),
    195: (None, "Fibrilación ventricular", "", C, "prior_arrhythmias = 1", None, None),
    196: (None, "Preexcitación tipo Wolff-Parkinson-White", "", C, "prior_arrhythmias = 1", None, None),
    # 7. Dispositivos
    198: (None, "Marcapasos", "", C, "", None, None),
    199: (None, "Desfibrilador automático implantable (DAI)", "", C, "", None, None),
    200: (None, "Marcapasos de resincronización (TRC-P)", "", C, "", None, None),
    201: (None, "Desfibrilador con resincronización (TRC-D)", "", C, "", None, None),
    # 8. Comorbilidades
    203: (None, "Enfermedad coronaria", "", C, "", None, None),
    204: (None, "Enfermedad arterial periférica", "", C, "", None, None),
    205: (None, "Valvulopatía moderada o grave (excluida la EAo índice)", "", C, "", None, None),
    206: (None, "Válvula aórtica bicúspide", "", C, "", None, None),
    207: (None, "Enfermedad renal crónica", "", C, "", None, None),
    208: (None, "Enfermedad pulmonar crónica", "", C, "", None, None),
    209: (None, "Hepatopatía crónica / cirrosis", "", C, "", None, None),
    210: (None, "Antecedente de sangrado mayor", "", C, "", None, None),
    211: (None, "Apnea obstructiva del sueño", "", C, "", None, None),
    212: (None, "Neoplasia maligna activa", "", C, "", None, None),
    213: (None, "Antecedente de neoplasia maligna", "", C, "", None, None),
    214: (None, "Quimioterapia previa o actual", "", C, "", None, None),
    215: (None, "Síndrome cardiorrenal", "", C, "", None, None),
    216: ("hypertension_treated_at_recruitment", "HTA con ≥1 fármaco en el momento del reclutamiento", "Solapa con hypertension_medication: revisar.", "ATTR", "", None, None),
    217: ("carpal_tunnel_syndrome", "Síndrome del túnel carpiano", "", "ATTR", "", None, None),
    218: ("lumbar_canal_stenosis", "Estenosis de canal lumbar", "", "ATTR", "", None, None),
    219: ("biceps_tendon_rupture", "Rotura atraumática del tendón del bíceps", "", "ATTR", "", None, None),
    220: ("polyneuropathy", "Polineuropatía", "", "ATTR", "", None, None),
    221: ("dysautonomia", "Disautonomía", "Ortostatismo, dishidrosis, disfunción eréctil, diarrea/estreñimiento, retención/incontinencia urinaria… por amiloidosis.", "ATTR", "", None, None),
    222: ("congestive_heart_failure", "Insuficiencia cardiaca congestiva", "Solapa con heart_failure: revisar.", "EAO", "", None, None),
    223: ("renal_disease", "Enfermedad renal", "Solapa con chronic_kidney_disease: revisar.", "EAO", "", None, None),
    224: ("left_ventricular_hypertrophy", "Hipertrofia ventricular izquierda", "", "IC", "", None, None),
    225: (None, "Otras comorbilidades relevantes (especificar)", "Texto libre; si es posible incluir código CIE-11.", C, "", None, None),
    # 9. Seguimiento
    227: ("follow_up_date", "Fecha del último seguimiento", "", C, "", None, None),
    228: (None, "Fallecimiento", "", C, "", None, None),
    229: (None, "Fecha de fallecimiento", "", C, "death = 1", None, None),
    230: ("rehospitalizations_number", "Número de reingresos", "", C, "", 0, 50),
    231: ("mace", "Eventos cardiovasculares y cerebrovasculares mayores (MACCE)", "Puede marcar varios; si es Sí se pide la fecha.", C, "", None, None),
    232: ("mace_myocardial_infarction", "Infarto de miocardio", "", C, "", None, None),
    233: ("mace_cardiac_arrest_sudden_death", "Parada cardiaca / muerte súbita", "", C, "", None, None),
    234: ("mace_heart_failure", "Insuficiencia cardiaca", "", C, "", None, None),
    235: ("mace_revascularization", "Revascularización (ICP / cirugía)", "", C, "", None, None),
    236: ("mace_stroke_tia", "Ictus / AIT", "", C, "", None, None),
    237: ("mace_other", "Otro evento (especificar)", "Texto libre; si es posible incluir código CIE-11.", C, "", None, None),
    238: ("eq5d_kccq_score", "Puntuación EQ-5D o KCCQ", "Aclarar qué escala se usa (rangos distintos).", C, "", 0, 100),
}

# Cabeceras de lista (enum): fila -> (filas_hijas, "única" | "múltiple")
ENUMS = {
    7: (range(8, 10), "única"),
    10: (range(11, 15), "múltiple"),
    15: (range(16, 20), "única"),
    22: (range(23, 25), "única"),
    27: (range(28, 36), "única"),
    36: (range(37, 40), "única"),
    49: (range(51, 54), "única"),  # 50 (disfunción VI) es ahora la pregunta llave
    57: (range(58, 60), "única"),
    60: (range(61, 63), "única"),
    65: (range(66, 69), "única"),
    71: (range(72, 74), "única"),
    78: (range(79, 81), "única"),
    89: (range(90, 96), "múltiple"),
    96: (range(97, 99), "múltiple"),
    111: (range(112, 116), "única"),
    117: (range(118, 122), "única"),
    122: (range(123, 127), "múltiple"),
    127: (range(128, 132), "única"),
    137: (range(138, 141), "única"),
    164: (range(165, 169), "única"),
    188: (range(189, 192), "única"),
    231: (range(232, 238), "múltiple"),
}

# Secciones (pestañas del formulario)
SECCIONES = {
    3: "0. Datos del caso",
    20: "1. Demografía y estilo de vida",
    42: "2. Diagnósticos",
    82: "2. Diagnósticos",  # bloque "otras variables ATTR"
    85: "2. Diagnósticos",  # bloque "otras variables IAM"
    99: "3. Pruebas diagnósticas",
    149: "4. Situación basal y constantes",
    154: "5. Factores de riesgo cardiovascular",
    163: "6. Historia cardiovascular",
    180: "6. Historia cardiovascular",
    197: "7. Dispositivos implantados",
    202: "8. Comorbilidades",
    226: "9. Seguimiento",
}

FLOAT_SIN_TIPO = set(range(101, 110)) | set(range(142, 148)) | {230}
FECHA_SIN_TIPO = {227}
ENTEROS = {86, 230}


def widget_y_export(tipo, codigo, es_cabecera_enum, modo_enum, es_hijo, fila):
    """Devuelve (control en pantalla, columnas que se exportan)."""
    tipo = (tipo or "").strip()
    if es_cabecera_enum:
        ctrl = "Selección única" if modo_enum == "única" else "Selección múltiple"
        # Algunas cabeceras llevan fecha (NYHA, TIMI, resultado genético)
        if tipo == "date":
            return ctrl + " + fecha", codigo
        return ctrl, "(no se exporta; se exportan las opciones)"
    if tipo == "boolean, date":
        if es_hijo:
            return "Opción (0/1) + fecha si 1", f"{codigo} ; {codigo}_date"
        return "Sí/No + fecha si Sí", f"{codigo} ; {codigo}_date"
    if tipo == "boolean":
        return ("Opción (0/1)" if es_hijo else "Sí/No"), codigo
    if tipo in ("date", "datetime"):
        return ("Fecha y hora (automática)" if tipo == "datetime" else "Fecha"), codigo
    if tipo == "float":
        return ("Número entero" if fila in ENTEROS else "Número"), codigo
    if tipo == "string":
        return "Texto", codigo
    return "?", codigo


def main(src, dst):
    wb = openpyxl.load_workbook(src, read_only=True)
    rows = list(wb["Data Dictionary"].iter_rows(values_only=True))

    hijos = {}
    for cab, (rng, modo) in ENUMS.items():
        for h in rng:
            hijos[h] = cab

    salida = []
    seccion = ""
    orden = 0
    for fila in range(3, len(rows) + 1):
        r = rows[fila - 1]
        disp, tipo, fmt, item = (r + (None,) * 4)[:4]
        if fila in SECCIONES:
            seccion = SECCIONES[fila]
        if fila not in T:
            continue
        cod_falta, es, ayuda, grupos, cond, vmin, vmax = T[fila]
        codigo = (item or "").split(";")[0].strip()
        nota_cod = ""
        if (item or "").count(";"):
            nota_cod = item.split(";", 1)[1].strip()
        provisional = ""
        if not codigo:
            codigo = cod_falta
            provisional = "PROVISIONAL"
        if not tipo:
            tipo = "float" if fila in FLOAT_SIN_TIPO else ("date" if fila in FECHA_SIN_TIPO else "")
        es_cab = fila in ENUMS
        modo = ENUMS[fila][1] if es_cab else ""
        padre = hijos.get(fila)
        ctrl, export = widget_y_export(tipo, codigo, es_cab, modo, padre is not None, fila)
        if fila == 5:
            ctrl, valor_fijo = "Fijo (no editable)", "ARRIXACA"
        else:
            valor_fijo = ""
        if fila == 6:
            ctrl = "Número entero (nº de caso)"
        unidades = (fmt or "").replace("true/false", "").strip(" ,;")
        if nota_cod:
            unidades = (unidades + "; " + nota_cod).strip("; ")
        orden += 1
        salida.append([
            orden, seccion, codigo, provisional,
            T[hijos[fila]][1] if padre else "",  # pregunta a la que pertenece
            (disp or "").strip(), es, ayuda, (tipo or "").strip(), unidades,
            ctrl, modo, grupos, cond, vmin, vmax, valor_fijo,
            "Sí", export, "", fila,
        ])
    write(dst, aplicar_propuesta(salida, SERGIO))


# ===========================================================================
#  Propuesta de agrupación por diagnóstico (Sergio, nov-2026)
# ===========================================================================
SERGIO = None  # ruta al Excel "WILLEM_propuesta_agrupacion_por_diagnostico"
COL_GRUPO = {"HF": "IC", "ATTR": "ATTR", "AS": "EAO", "HCM": "MCH", "MI": "IAM", "Long QT": "QTL"}


# Pestañas del formulario (nov-2026): fusión de bloques. (pestaña, [bloques de Sergio en orden])
PESTANAS = [
    ("1. Datos del paciente", ["01. Metadatos", "02. Demografía y hábitos"]),
    ("2. Diagnósticos", ["03. Diagnóstico y clasificación", "04. ATTR: marcadores", "05. MI: gravedad y tratamiento"]),
    ("3. Situación basal y constantes", ["15. Constantes"]),
    ("4. Antecedentes y comorbilidades", ["16. Factores de riesgo cardiovascular", "17. Historia cardiovascular", "19. Comorbilidades"]),
    ("5. Procedimientos diagnósticos y dispositivos", ["14. Analítica y ECG", "06. Conducción y ECG", "08. Ecocardiograma general",
                                                       "09. Eco estenosis aórtica", "11. Coronariografía / MI", "05. MI: revascularización",
                                                       "10. ATTR: gammagrafía", "12. ATTR: biopsia", "13. Genética", "18. Dispositivos"]),
    ("6. Seguimiento", ["20. Seguimiento"]),
]
NOMBRE_BLOQUE = {"Coronariografía / MI": "Coronariografía", "MI: revascularización": "Revascularización coronaria",
                 "ATTR: gammagrafía": "Gammagrafía", "ATTR: biopsia": "Biopsia", "Genética": "Estudio genético",
                 "Analítica y ECG": "Analítica", "Conducción y ECG": "Conducción (ECG)",
                 "Eco estenosis aórtica": "Ecocardiograma: estenosis aórtica"}

# Reglas acordadas (fila del diccionario -> cambios)
REGLAS = {
    5: {"valor_fijo": "HCUVA", "ayuda_ES": "Fijo: HCUVA."},
    11: {"valor_por_defecto": 1}, 12: {"valor_por_defecto": 1}, 13: {"valor_por_defecto": 1},
    14: {"valor_por_defecto": "patient_group_retrospective = 1 -> 0 ; patient_group_prospective = 1 -> 1",
         "ayuda_ES": "Por defecto: No si es retrospectivo, Sí si es prospectivo."},
    40: {"mostrar_solo_si": "patient_group_prospective = 1"},
    41: {"mostrar_solo_si": "patient_group_prospective = 1"},
    49: {"mostrar_solo_si": "heart_failure_lvef = 1", "texto_ES": "Tipo según FEVI"},
    50: {"texto_ES": "Disfunción ventricular izquierda", "tipo_formulario": "boolean, date"},
    111: {"mostrar_solo_si": "scintigraphy_procedure_done = 1"},
    117: {"mostrar_solo_si": "coronary_angiography_done = 1"},
    122: {"mostrar_solo_si": "coronary_angiography_done = 1"},
    127: {"mostrar_solo_si": "coronary_angiography_done = 1", "tipo_formulario": "enum",
          "copiar_de": "coronary_angiography_done_date", "texto_ES": "Flujo TIMI"},
    133: {"mostrar_solo_si": "biopsy_procedure_done = 1"},
    135: {"mostrar_solo_si": "genetic_screening_procedure_done = 1"},
    136: {"oculto": "Sí", "copiar_de": "genetic_screening_hcm_result_positive",
          "ayuda_ES": "Se calcula: 1 si el resultado genético de MCH es positivo."},
    137: {"mostrar_solo_si": "genetic_screening_procedure_done = 1", "tipo_formulario": "enum",
          "copiar_de": "genetic_screening_procedure_done_date", "texto_ES": "Resultado del estudio genético (MCH)"},
    142: {"oculto": "Sí", "ayuda_ES": "No se mide BNP en nuestro laboratorio: se deja en blanco."},
    144: {"oculto": "Sí", "ayuda_ES": "No se mide troponina I en nuestro laboratorio: se deja en blanco."},
    148: {"oculto": "Sí", "ayuda_ES": "La fecha del ECG vendrá con los datos del iECG."},
    164: {"tipo_formulario": "enum", "copiar_de": "baseline_status", "texto_ES": "Clase funcional NYHA",
          "ayuda_ES": "La fecha se toma de la valoración basal."},
    191: {"texto_ES": "Permanente o crónica"},
    196: {"mostrar_solo_si": "prior_arrhythmias = 1"},
    198: {"mostrar_solo_si": "implanted_cardiovascular_devices = 1"},
    199: {"mostrar_solo_si": "implanted_cardiovascular_devices = 1"},
    200: {"mostrar_solo_si": "implanted_cardiovascular_devices = 1"},
    201: {"mostrar_solo_si": "implanted_cardiovascular_devices = 1"},
    223: {"oculto": "Sí", "copiar_de": "chronic_kidney_disease", "ayuda_ES": "Se copia de Enfermedad renal crónica."},
    # Isquémica e infarto: mismos campos, sin depender de "infarto = Sí"
    44: {"patologias": "ISQ IAM", "mostrar_solo_si": ""},
    56: {"patologias": "ISQ IAM", "mostrar_solo_si": ""},
    57: {"mostrar_solo_si": ""}, 58: {"mostrar_solo_si": ""}, 59: {"mostrar_solo_si": ""},
    60: {"mostrar_solo_si": ""}, 61: {"mostrar_solo_si": ""}, 62: {"mostrar_solo_si": ""},
    86: {"mostrar_solo_si": ""}, 87: {"mostrar_solo_si": ""}, 88: {"mostrar_solo_si": ""},
    # Los diagnósticos solo se preguntan al principio: los duplicados se copian
    81: {"oculto": "Sí", "ayuda_ES": "Se rellena al elegir 'Otros' en los diagnósticos del caso."},
    173: {"oculto": "Sí", "copiar_de": "long_qt_syndrome", "ayuda_ES": "Se copia del diagnóstico inicial."},
    222: {"oculto": "Sí", "copiar_de": "heart_failure", "ayuda_ES": "Se copia del diagnóstico inicial."},
    # Seguimiento: el fallecimiento es un evento más, con su fecha
    228: {"texto_ES": "Fallecimiento", "tipo_formulario": "boolean, date"},
    229: {"oculto": "Sí", "copiar_de": "death_date", "ayuda_ES": "Fecha del evento 'Fallecimiento'."},
    231: {"texto_ES": "Eventos durante el seguimiento", "ayuda_ES": "Marque todos los que haya habido y la fecha de cada uno."},
    225: {"oculto": "Sí"}, 237: {"oculto": "Sí"}, 238: {"oculto": "Sí"},
}

# Preguntas llave nuevas (variables propias, no se envían). fila -> (código, texto, ¿con fecha?)
# Si la fila original es una fecha del registro, se oculta y se copia de la fecha de la llave.
PUERTAS = {
    110: ("scintigraphy_procedure_done", "¿Se realizó gammagrafía?", True),
    116: ("coronary_angiography_done", "¿Se realizó coronariografía?", True),
    132: ("biopsy_procedure_done", "¿Se realizó biopsia?", True),
    134: ("genetic_screening_procedure_done", "¿Se realizó estudio genético?", True),
    198: ("implanted_cardiovascular_devices", "¿Tiene algún dispositivo cardiaco implantado?", False),
}


def leer_propuesta(ruta):
    ws = openpyxl.load_workbook(ruta, read_only=True).worksheets[0]
    filas = list(ws.iter_rows(values_only=True))
    cab = [str(c or "").strip() for c in filas[0]]
    ix = {c: i for i, c in enumerate(cab)}
    out = {}
    for r in filas[1:]:
        if not r or r[0] is None:
            continue
        grupos = [g for col, g in COL_GRUPO.items() if str(r[ix[col]] or "").strip() not in ("", "—", "-", "0")]
        out[int(r[0])] = {"bloque": str(r[ix["Bloque propuesto"]] or "").strip(), "grupos": grupos,
                          "tipo": str(r[ix["Tipo / unidad"]] or "")}
    return out


def control_formulario(d):
    tf, es_hijo = d["tipo_formulario"], bool(d["pertenece_a_pregunta"])
    if d["tipo_seleccion"]:
        base = "Selección única" if d["tipo_seleccion"] == "única" else "Selección múltiple"
        return base + (" + fecha" if tf == "date" else "")
    if d["valor_fijo"]:
        return "Fijo (no editable)"
    if tf == "boolean, date":
        return "Opción (0/1) + fecha si 1" if es_hijo else "Sí/No + fecha si Sí"
    if tf == "boolean":
        return "Opción (0/1)" if es_hijo else "Sí/No"
    return d["control_en_pantalla"]


def aplicar_propuesta(salida, ruta):
    prop = leer_propuesta(ruta) if ruta else {}
    out = []
    for lst in salida:
        d = dict(zip(CABECERA_BASE, lst[:len(CABECERA_BASE)]))
        fila = lst[len(CABECERA_BASE)]
        d.update(tipo_formulario=d["tipo"], oculto="", valor_por_defecto="", copiar_de="")
        p = prop.get(fila)
        if p:
            d["pestaña"] = p["bloque"] or d["pestaña"]
            d["patologias"] = "COMUN" if len(p["grupos"]) == 6 else " ".join(p["grupos"])
            if d["tipo"] == "boolean, date" and p["tipo"].startswith("boolean ·"):
                d["tipo_formulario"] = "boolean"  # sin fecha
        # Cardiopatía isquémica e infarto ven exactamente los mismos campos
        if "IAM" in d["patologias"].split() and "ISQ" not in d["patologias"].split():
            d["patologias"] = (d["patologias"] + " ISQ").strip()
        d.update(REGLAS.get(fila, {}))
        d["_fila"] = fila
        if fila in PUERTAS:
            cod, texto, con_fecha = PUERTAS[fila]
            t = "boolean, date" if con_fecha else "boolean"
            puerta = {k: "" for k in CABECERA}
            puerta.update({"pestaña": d["pestaña"], "codigo_variable": cod, "codigo_provisional": "LOCAL",
                           "texto_ES": texto, "tipo": t, "tipo_formulario": t, "patologias": d["patologias"],
                           "exportar_al_registro": "Solo local",
                           "columnas_en_exportacion": f"{cod} ; {cod}_date" if con_fecha else cod,
                           "ayuda_ES": "Pregunta propia de la base (no va al registro): abre los campos de esta prueba."})
            puerta["control_en_pantalla"] = control_formulario(puerta)
            out.append(puerta)
            if con_fecha:  # la fecha del registro sale de la fecha de la pregunta llave
                d.update(oculto="Sí", copiar_de=f"{cod}_date")
        d["control_en_pantalla"] = control_formulario(d)
        out.append(d)
    # Pregunta llave delante de su lista: "Disfunción VI" (50) antes de "Tipo según FEVI" (49)
    llave_vi = next((d for d in out if d.get("_fila") == 50), None)
    tipo_fevi = next((d for d in out if d.get("_fila") == 49), None)
    if llave_vi and tipo_fevi:
        out.remove(llave_vi)
        out.insert(out.index(tipo_fevi), llave_vi)
    # Orden del CRF original: el Excel final se exporta siempre en este orden
    for d in out:
        d["orden_registro"] = d.get("_fila") if d.get("exportar_al_registro") == "Sí" else ""
    # Fallecimiento como opción de "Eventos durante el seguimiento"
    muerte = next((d for d in out if d.get("_fila") == 228), None)
    eventos = next((d for d in out if d.get("_fila") == 231), None)
    if muerte and eventos:
        muerte["pertenece_a_pregunta"] = eventos["texto_ES"]
        muerte["control_en_pantalla"] = control_formulario(muerte)
        out.remove(muerte)
        out.insert(out.index(eventos) + 1, muerte)
    # Pestañas fusionadas y orden de bloques
    pos_bloque = {b: (ti, bi) for ti, (_, bloques) in enumerate(PESTANAS) for bi, b in enumerate(bloques)}
    nombre_tab = {b: t for t, bloques in PESTANAS for b in bloques}
    for i, d in enumerate(out):
        b = d["pestaña"]
        d["_orden"] = (*pos_bloque.get(b, (99, 99)), i)
        limpio = re.sub(r"^\d+\.\s*", "", b)
        d["bloque"] = NOMBRE_BLOQUE.get(limpio, limpio)
        d["pestaña"] = nombre_tab.get(b, b)
    out.sort(key=lambda d: d["_orden"])
    for i, d in enumerate(out, 1):
        d["orden"] = i
        d.pop("_orden", None)
        d.pop("_fila", None)
    return out


CABECERA_BASE = [
    "orden", "pestaña", "codigo_variable", "codigo_provisional", "pertenece_a_pregunta",
    "texto_original_EN", "texto_ES", "ayuda_ES", "tipo", "formato_unidades_notas",
    "control_en_pantalla", "tipo_seleccion", "patologias", "mostrar_solo_si",
    "valor_min", "valor_max", "valor_fijo", "exportar_al_registro",
    "columnas_en_exportacion", "comentarios_equipo",
]
CABECERA = CABECERA_BASE[:2] + ["bloque"] + CABECERA_BASE[2:-1] + ["tipo_formulario", "oculto", "valor_por_defecto", "copiar_de", "orden_registro", "comentarios_equipo"]
ANCHOS = [6, 30, 26, 38, 13, 30, 45, 45, 40, 13, 22, 26, 12, 16, 34, 9, 9, 11, 11, 44, 16, 9, 22, 30, 10, 40]


def estilo_cabecera(ws, ncols):
    fill = PatternFill("solid", fgColor="1F4E79")
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = "D2"
    ws.row_dimensions[1].height = 32


def write(dst, salida):
    out = openpyxl.Workbook()

    # --- Leyenda --------------------------------------------------------
    ley = out.active
    ley.title = "LEEME"
    lineas = [
        ("DICCIONARIO MAESTRO – Registro WILLEM (Hospital Virgen de la Arrixaca)", True),
        ("", False),
        ("Qué es: la lista de TODOS los campos del formulario. La aplicación se construye leyendo este Excel.", False),
        ("Cómo revisarlo: corrija libremente las columnas en AMARILLO y escriba dudas en 'comentarios_equipo'.", False),
        ("NO cambie 'codigo_variable' salvo los marcados PROVISIONAL (no tienen código en el CRF oficial).", False),
        ("", False),
        ("COLUMNAS", True),
        ("texto_ES / ayuda_ES: lo que verá la persona que introduce los datos.", False),
        ("patologias: en qué grupos se muestra el campo (pueden ser varios, separados por espacio).", False),
        ("mostrar_solo_si: condición adicional (p. ej. la fecha del IAM solo si IAM = 1).", False),
        ("valor_min / valor_max: rango admitido; fuera de rango la aplicación avisa.", False),
        ("exportar_al_registro: 'Sí' = va al Excel final; 'Solo local' = dato propio que guardamos pero no enviamos.", False),
        ("columnas_en_exportacion: nombre exacto de la(s) columna(s) en el archivo final (1 fila = 1 paciente).", False),
        ("tipo_formulario: cómo se pregunta en pantalla ('boolean' = Sí/No sin fecha aunque el registro tenga columna de fecha, que irá vacía).", False),
        ("oculto: 'Sí' = no se muestra en el formulario (se exporta vacío o calculado).", False),
        ("valor_por_defecto: valor al crear el caso; o regla 'campo = 1 -> valor ; otro = 1 -> valor'.", False),
        ("copiar_de: el valor se calcula copiando otro campo (p. ej. enfermedad renal = ERC).", False),
        ("", False),
        ("GRUPOS DE PATOLOGÍA", True),
    ] + [(f"{k}: {v}", False) for k, v in GRUPOS.items()] + [
        ("", False),
        ("REGLAS ACORDADAS", True),
        ("• Sí = 1, No = 0. Si se marca Sí en un campo con fecha, se abre la fecha; si No, no.", False),
        ("• Desconocido y Duda en todos los Sí/No y listas: en el Excel final van vacíos; Duda impide validar el caso.", False),
        ("• Agrupación por diagnóstico según la propuesta de Sergio (nov-2026).", False),
        ("• Campo que nadie toca = vacío ('no consta'). Solo se pone 0 al pulsar 'Marcar el resto como No'.", False),
        ("• Listas de selección única (raza, sexo, NYHA…): se elige una y se exporta 1 en esa y 0 en las demás.", False),
        ("• Solo ecocardiograma basal; no hay ecos evolutivos.", False),
        ("• Los datos extra de interés que no están en el CRF se añaden en la hoja 'Variables_locales'.", False),
        ("• El número de caso NUNCA es el CIP/CARM/NHC: la correspondencia se guarda aparte, offline.", False),
    ]
    for i, (txt, neg) in enumerate(lineas, 1):
        c = ley.cell(row=i, column=1, value=txt)
        c.font = Font(bold=neg, size=13 if i == 1 else 11)
    ley.column_dimensions["A"].width = 120

    # --- Diccionario ----------------------------------------------------
    ws = out.create_sheet("Diccionario")
    ws.append(CABECERA)
    for fila in salida:
        ws.append([fila.get(k, "") for k in CABECERA])
    estilo_cabecera(ws, len(CABECERA))
    for i, w in enumerate(ANCHOS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    amarillo = PatternFill("solid", fgColor="FFF2CC")
    gris = PatternFill("solid", fgColor="EDEDED")
    rojo = PatternFill("solid", fgColor="F8CBAD")
    editables = {CABECERA.index(k) + 1 for k in ("texto_ES", "ayuda_ES", "patologias", "mostrar_solo_si", "valor_min", "valor_max",
                                                 "exportar_al_registro", "tipo_formulario", "oculto", "valor_por_defecto", "copiar_de", "comentarios_equipo")}
    fino = Side(style="thin", color="BFBFBF")
    for r in range(2, ws.max_row + 1):
        es_cab = ws.cell(r, 12).value and not ws.cell(r, 5).value
        for c in range(1, len(CABECERA) + 1):
            cell = ws.cell(r, c)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = Border(bottom=fino)
            if c in editables:
                cell.fill = amarillo
            elif es_cab:
                cell.fill = gris
        if ws.cell(r, 4).value:
            ws.cell(r, 4).fill = rojo
        if ws.cell(r, CABECERA.index("oculto") + 1).value == "Sí":
            ws.cell(r, 7).font = Font(color="999999", italic=True)
        if es_cab:
            ws.cell(r, 7).font = Font(bold=True)
    dv = DataValidation(type="list", formula1='"Sí,Solo local,No"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"R2:R{ws.max_row}")
    dv2 = DataValidation(type="list", formula1='"Sí,"', allow_blank=True)
    ws.add_data_validation(dv2)
    col_oc = get_column_letter(CABECERA.index("oculto") + 1)
    dv2.add(f"{col_oc}2:{col_oc}{ws.max_row}")
    ws.auto_filter.ref = f"A1:{get_column_letter(len(CABECERA))}{ws.max_row}"

    # --- Variables locales (datos extra) --------------------------------
    vl = out.create_sheet("Variables_locales")
    vl.append(CABECERA)
    estilo_cabecera(vl, len(CABECERA))
    for i, w in enumerate(ANCHOS, 1):
        vl.column_dimensions[get_column_letter(i)].width = w
    ej = {"codigo_variable": "local_ejemplo_tapse", "texto_ES": "Ejemplo: TAPSE (mm)",
          "ayuda_ES": "Borre esta fila y añada las variables que queráis recoger además del CRF.",
          "tipo": "float", "tipo_formulario": "float", "formato_unidades_notas": "mm", "control_en_pantalla": "Número",
          "patologias": "COMUN", "valor_min": 5, "valor_max": 40, "exportar_al_registro": "Solo local",
          "columnas_en_exportacion": "local_ejemplo_tapse"}
    vl.append([ej.get(k, "") for k in CABECERA])

    # --- Plantilla de exportación ---------------------------------------
    ex = out.create_sheet("Plantilla_exportacion")
    cols = []
    for f in sorted(salida, key=lambda d: d.get("orden_registro") or 99999):
        exp = f["columnas_en_exportacion"]
        if exp.startswith("(") or f["exportar_al_registro"] != "Sí":
            continue
        cols += [c.strip() for c in exp.split(";")]
    ex.append(cols)
    for i in range(1, len(cols) + 1):
        ex.cell(1, i).font = Font(bold=True)
        ex.column_dimensions[get_column_letter(i)].width = max(12, len(cols[i - 1]) + 2)
    ex.freeze_panes = "D2"

    # --- Dudas abiertas ---------------------------------------------------
    du = out.create_sheet("Dudas")
    du.append(["#", "Duda", "Propuesta", "Decisión del equipo"])
    dudas = [
        ("Campos 'boolean, date': ¿se exportan como 2 columnas (codigo = 0/1 y codigo_date)?",
         "Sí, 2 columnas. Ver hoja Plantilla_exportacion."),
        ("Variables sin código en el CRF oficial (marcadas PROVISIONAL).",
         "Usar los códigos propuestos; confirmar con el coordinador del registro si los acepta."),
        ("Duplicados: QT largo, WPW, TV polimórfica, FV (en Diagnóstico/Historia y en Eventos previos); "
         "ICC vs heart_failure; enfermedad renal vs ERC; HTA tratada vs tratamiento antihipertensivo.",
         "Mostrar UNA pregunta y rellenar ambas columnas automáticamente."),
        ("Seguimiento: ¿un único bloque (último seguimiento) o uno por año (año 1, 2, 3…)?",
         "Un único bloque con la fecha del primer evento de cada tipo."),
        ("EQ-5D (índice -0,6 a 1 o EVA 0–100) y KCCQ (0–100) tienen escalas distintas.",
         "Separar en dos campos o fijar una sola escala."),
        ("Fecha de nacimiento en la base online: es un dato muy identificativo junto con fechas de eventos.",
         "Consultar con el CEIm/DPD; el registro la pide, así que se exporta igual."),
        ("Fibrilación auricular como grupo propio de patología (comentado en la reunión).",
         "De momento está en Historia cardiovascular para todos; si queréis campos específicos de FA, añadir en Variables_locales."),
    ]
    for i, (d, p) in enumerate(dudas, 1):
        du.append([i, d, p, ""])
    for col, w in zip("ABCD", [4, 70, 60, 40]):
        du.column_dimensions[col].width = w
    for row in du.iter_rows(min_row=1):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    estilo_cabecera(du, 4)

    out.save(dst)
    print(f"OK: {len(salida)} campos, {len(cols)} columnas de exportación -> {dst}")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    if len(sys.argv) == 4:
        SERGIO = sys.argv[3]
    main(sys.argv[1], sys.argv[2])
