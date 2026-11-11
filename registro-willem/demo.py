"""
Pacientes INVENTADOS para la demostración (python servidor.py --demo).
Nada de esto corresponde a personas reales.
"""
import datetime as dt
import json
import random
import sqlite3

USUARIOS = [
    ("admin", "Data manager (demo)", "dm", "willem2026"),
    ("lucia", "Lucía Martínez (demo)", "dm", "willem2026"),
    ("carmen", "Carmen Ruiz (demo)", "intro", "willem2026"),
    ("ana", "Ana López (demo)", "intro", "willem2026"),
]


def _f(d):
    return d.strftime("%Y-%m-%d")


def _valores(rnd, principal, hoy):
    v = {}
    edad = rnd.randint(48, 88)
    nac = hoy - dt.timedelta(days=edad * 365 + rnd.randint(0, 364))
    fecha_dx = hoy - dt.timedelta(days=rnd.randint(30, 2500))
    v["dob"] = _f(nac)
    varon = rnd.random() < 0.62
    v["biological_sex_male"], v["biological_sex_female"] = (1, 0) if varon else (0, 1)
    v["height"] = rnd.randint(165, 185) if varon else rnd.randint(150, 170)
    v["weight"] = rnd.randint(60, 105)
    razas = ["racial_group_african_race", "racial_group_american_indian_race", "racial_group_asian_race",
             "racial_group_caucasian", "racial_group_hispanic", "racial_group_pacific_islander",
             "racial_group_mixed", "racial_group_unknown"]
    elegida = "racial_group_caucasian" if rnd.random() < 0.85 else "racial_group_hispanic"
    for r in razas:
        v[r] = 1 if r == elegida else 0
    tab = rnd.choice(["tobacco_habit_smoker", "tobacco_habit_ex_smoker", "tobacco_habit_non_smoker"])
    for t in ["tobacco_habit_smoker", "tobacco_habit_ex_smoker", "tobacco_habit_non_smoker"]:
        v[t] = 1 if t == tab else 0
    v["patient_group_retrospective"], v["patient_group_prospective"] = (1, 0) if rnd.random() < 0.7 else (0, 1)
    for k in ["eligibility_criteria_age", "eligibility_criteria_ecg", "eligibility_criteria_disease"]:
        v[k] = 1
    v["eligibility_criteria_icf"] = v["patient_group_prospective"]
    amb = rnd.choice(["patient_care_setting_inpatient", "patient_care_setting_outpatient"])
    for k in ["patient_care_setting_inpatient", "patient_care_setting_outpatient", "patient_care_setting_emergency", "patient_care_setting_unknown"]:
        v[k] = 1 if k == amb else 0

    eco = fecha_dx + dt.timedelta(days=rnd.randint(0, 20))
    v["echocardiography_procedure"] = _f(eco)
    v["echocardiography_lvedd"] = rnd.randint(44, 66)
    v["laboratory_biomarkers_test"] = _f(eco)
    v["natriuretic_peptide_nt_probnp"] = rnd.randint(150, 9000)
    v["creatinine"] = round(rnd.uniform(0.7, 2.1), 2)
    v["glomerular_filtration_rate_mdrd"] = rnd.randint(28, 95)
    v["baseline_status"] = _f(eco)
    v["systolic_blood_pressure_mean"] = rnd.randint(100, 160)
    v["diastolic_blood_pressure_mean"] = rnd.randint(55, 95)
    v["resting_heart_rate"] = rnd.randint(55, 98)
    for k in ["hypertension", "diabetes_mellitus_type_2", "dyslipidaemia", "clinically_diagnosed_obesity"]:
        si = rnd.random() < 0.55
        v[k] = 1 if si else 0
    v["diabetes_mellitus_type_1"] = 0

    if principal == "IC":
        fevi = rnd.choice([28, 32, 35, 38, 45, 47, 55, 60])
        v["echocardiography_lvef"] = fevi
        v["heart_failure_diagnosis_date"] = _f(fecha_dx)
        tipo = "heart_failure_lvef_reduced" if fevi <= 40 else ("heart_failure_lvef_midrange" if fevi < 50 else "heart_failure_lvef_preserved")
        v["heart_failure_lvef"], v["heart_failure_lvef_date"] = 1, _f(fecha_dx)
        for k in ["heart_failure_lvef_reduced", "heart_failure_lvef_midrange", "heart_failure_lvef_preserved"]:
            v[k] = 1 if k == tipo else 0
        v["echocardiography_lv_global_longitudinal_strain"] = -rnd.randint(8, 17)
        n = rnd.choice(["nyha_class_ii", "nyha_class_ii", "nyha_class_iii", "nyha_class_i"])
        for k in ["nyha_class_i", "nyha_class_ii", "nyha_class_iii", "nyha_class_iv"]:
            v[k] = 1 if k == n else 0
    elif principal == "ISQ":
        v["echocardiography_lvef"] = rnd.randint(35, 62)
        v["ischemic_cardiomyopathy_diagnosis_date"] = _f(fecha_dx)
        v["myocardial_infarction"] = 1
        v["myocardial_infarction_diagnosis_date"] = _f(fecha_dx)
        st = rnd.random() < 0.5
        v["myocardial_infarction_stemi"], v["myocardial_infarction_nstemi"] = (1, 0) if st else (0, 1)
        v["coronary_angiography_done"], v["coronary_angiography_done_date"] = 1, _f(fecha_dx)
        v["coronary_occlusion_lad"] = 1 if rnd.random() < 0.5 else 0
        v["coronary_occlusion_rca"] = 1 - v["coronary_occlusion_lad"]
        v["coronary_occlusion_lcx"] = 0
        v["coronary_occlusion_unknown"] = 0
        v["mi_number_of_stents"] = rnd.randint(1, 3)
        v["coronary_revascularization_pci"] = 1
        v["coronary_revascularization_cabg"] = 0
        v["troponin_t_hs"] = rnd.randint(200, 6000)
    elif principal == "EAO":
        v["echocardiography_lvef"] = rnd.randint(50, 68)
        v["aortic_stenosis_diagnosis_date"] = _f(fecha_dx)
        sev = rnd.choice(["aortic_stenosis_mild", "aortic_stenosis_moderate", "aortic_stenosis_severe", "aortic_stenosis_severe"])
        for k in ["aortic_stenosis_mild", "aortic_stenosis_moderate", "aortic_stenosis_severe"]:
            v[k] = 1 if k == sev else 0
        vmax = {"aortic_stenosis_mild": 2.8, "aortic_stenosis_moderate": 3.5, "aortic_stenosis_severe": 4.4}[sev]
        v["echocardiography_aortic_vmax"] = round(vmax + rnd.uniform(-0.2, 0.3), 1)
        v["echocardiography_aortic_mean_gradient"] = int(4 * v["echocardiography_aortic_vmax"] ** 2 * 0.6)
        v["echocardiography_aortic_valve_area"] = round({"aortic_stenosis_mild": 1.6, "aortic_stenosis_moderate": 1.2, "aortic_stenosis_severe": 0.8}[sev], 2)
        v["echocardiography_septal_thickness_plax"] = rnd.randint(11, 14)
        v["echocardiography_posterior_wall_thickness_plax"] = rnd.randint(10, 13)
    elif principal == "MCH":
        v["echocardiography_lvef"] = rnd.randint(60, 72)
        v["hypertrophic_cardiomyopathy_diagnosis_date"] = _f(fecha_dx)
        obs = rnd.random() < 0.4
        v["hypertrophic_cardiomyopathy_obstructive"], v["hypertrophic_cardiomyopathy_non_obstructive"] = (1, 0) if obs else (0, 1)
        v["echocardiography_max_lv_wall_thickness"] = rnd.randint(16, 28)
        v["echocardiography_septal_thickness_plax"] = v["echocardiography_max_lv_wall_thickness"]
        v["family_history_hcm"] = 1 if rnd.random() < 0.3 else 0
    elif principal == "QTL":
        v["echocardiography_lvef"] = rnd.randint(55, 68)
        v["long_qt_syndrome_diagnosis_date"] = _f(fecha_dx)
        v["history_syncope"] = 1 if rnd.random() < 0.5 else 0
        v["genetic_screening_procedure_done"], v["genetic_screening_procedure_done_date"] = 1, _f(fecha_dx)
    elif principal == "ATTR":
        v["echocardiography_lvef"] = rnd.randint(40, 60)
        v["amyloidosis_attr_diagnosis_date"] = _f(fecha_dx)
        wt = rnd.random() < 0.8
        v["amyloidosis_attr_wild"], v["amyloidosis_attr_variant"] = (1, 0) if wt else (0, 1)
        v["scintigraphy_procedure_done"], v["scintigraphy_procedure_done_date"] = 1, _f(fecha_dx)
        g = rnd.choice(["scintigraphy_perugini_score_grade_2", "scintigraphy_perugini_score_grade_3"])
        for k in ["scintigraphy_perugini_score_grade_0", "scintigraphy_perugini_score_grade_1",
                  "scintigraphy_perugini_score_grade_2", "scintigraphy_perugini_score_grade_3"]:
            v[k] = 1 if k == g else 0
        v["echocardiography_max_lv_wall_thickness"] = rnd.randint(14, 20)
        v["echocardiography_lv_global_longitudinal_strain"] = -rnd.randint(8, 14)
        v["carpal_tunnel_syndrome"] = 1 if rnd.random() < 0.5 else 0
        v["ecg_low_voltage"] = 1 if rnd.random() < 0.4 else 0
        v["amyloidosis_attr_mgus"] = 0
    return v


def poblar(ruta_db, ruta_llave, hash_pw, diagnosticos):
    con = sqlite3.connect(ruta_db)
    if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
        con.close()
        return
    rnd = random.Random(2026)
    hoy = dt.date.today()
    with con:
        for u, n, r, c in USUARIOS:
            con.execute("INSERT INTO usuarios(usuario,nombre,rol,hash,creado) VALUES(?,?,?,?,?)",
                        (u, n, r, hash_pw(c), dt.datetime.now().isoformat(timespec="seconds")))
        plan = ["IC"] * 9 + ["ISQ"] * 8 + ["EAO"] * 4 + ["MCH"] * 3 + ["ATTR"] * 3 + ["QTL"] * 2
        rnd.shuffle(plan)
        llave = sqlite3.connect(ruta_llave)
        llave.execute("""CREATE TABLE IF NOT EXISTS llave(numero INTEGER PRIMARY KEY, cip TEXT, carm TEXT, nhc TEXT,
                         notas TEXT, creado TEXT, creado_por TEXT)""")
        for i, principal in enumerate(plan, 1):
            sec = []
            if rnd.random() < 0.3:
                sec = [rnd.choice([g for g in ["IC", "ISQ", "EAO", "ATTR"] if g != principal])]
            v = {"site_id": "HCUVA", "patient_id": i}
            v.update(diagnosticos(principal, sec))
            v.update(_valores(rnd, principal, hoy))
            # Algunas respuestas "Desconocido" y "Duda"
            if rnd.random() < 0.4:
                v["family_history_heart_disease"] = "NC"
            if rnd.random() < 0.15:
                v["clinically_diagnosed_obesity"] = "DUDA"
                v["clinically_diagnosed_obesity_duda_nota"] = rnd.choice(["IMC 29,8: ¿cuenta como obesidad?", "Solo consta 'sobrepeso' en el informe"])
            # Algunos casos a medio rellenar
            if rnd.random() < 0.35:
                for k in rnd.sample(sorted(v), k=len(v) // 3):
                    if k not in ("site_id", "patient_id") and not k.startswith(("heart_failure", "aortic_stenosis", "amyloidosis", "hypertrophic", "ischemic", "long_qt")):
                        v.pop(k, None)
            creado = dt.datetime.combine(hoy - dt.timedelta(days=rnd.randint(1, 75)), dt.time(rnd.randint(8, 14), rnd.randint(0, 59)))
            mod = creado + dt.timedelta(days=rnd.randint(0, 10), hours=rnd.randint(0, 5))
            if mod.date() > hoy:
                mod = dt.datetime.now() - dt.timedelta(hours=rnd.randint(1, 30))
            v["authored_at"] = creado.isoformat(timespec="seconds")
            estado = rnd.choice(["borrador", "completo", "completo", "validado"])
            if estado == "validado" and "DUDA" in v.values():
                estado = "completo"
            quien = rnd.choice(["carmen", "ana", "lucia"])
            con.execute("""INSERT INTO casos(numero,principal,secundarias,valores,estado,creado,creado_por,modificado,modificado_por)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (i, principal, json.dumps(sec), json.dumps(v), estado, creado.isoformat(timespec="seconds"),
                         quien, mod.isoformat(timespec="seconds"), quien))
            con.execute("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                        (i, quien, creado.isoformat(timespec="seconds"), "(caso creado)", None, principal, "formulario"))
            for k in rnd.sample([k for k in v if k not in ("site_id", "patient_id", "authored_at")], k=4):
                con.execute("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                            (i, quien, mod.isoformat(timespec="seconds"), k, None, str(v[k]), rnd.choice(["formulario", "importacion"])))
            llave.execute("INSERT INTO llave VALUES(?,?,?,?,?,?,?)",
                          (i, f"DEMO{rnd.randint(10**9, 10**10 - 1)}", None, f"{rnd.randint(100000, 999999)}",
                           "Paciente ficticio", creado.isoformat(timespec="seconds"), "lucia"))
        llave.commit()
        llave.close()
    con.close()
