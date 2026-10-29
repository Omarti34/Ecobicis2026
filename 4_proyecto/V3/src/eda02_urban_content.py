"""Additional Spanish sections, inserted without rewriting existing code cells."""
from textwrap import dedent

from V3.src.eda02_content import get_notebook_cells


def _section(markdown, code):
    return [("markdown", dedent(markdown).strip()), ("code", dedent(code).strip())]


def get_enriched_notebook_cells():
    additions = {
        "## 4. Concentración": _section("""
        ### 3.1. Dinámica intradiaria: laborables y fines de semana

        El pulso horario se calcula sobre retiros y arribos válidos de 2025 asociados
        al catálogo, conservando la misma cohorte de extremos del diagnóstico anual.
        Se leen por bloques los doce meses aceptados y se incorporan los extremos
        válidos conocidos de viajes en cuarentena con sus pesos fraccionales. No
        se cuentan códigos desconocidos ni se duplican estaciones con alias.
        La suma horaria debe coincidir con los totales anuales ETL de cada rol.

        Cada extremo utiliza su propia fecha y hora local de Ciudad de México.
        Laborables significa lunes a viernes, incluyendo feriados; fin de semana
        significa sábado y domingo. Se divide cada conteo horario entre el número
        de días de su clase durante 2025, incluyendo días sin registros. Así la
        comparación no confunde cinco días semanales con dos.

        Los picos AM/PM permiten explorar compatibilidad con movilidad pendular;
        una concentración diurna en fines de semana puede ser compatible con usos
        recreativos. La curva no identifica propósitos individuales de viaje ni
        mide demanda latente o inventario disponible.
        """, """
        from V3.src.eda02_urban import (
            URBAN_VERSION, URBAN_CONFIG, hourly_profile, census_population, modal_proximity,
        )

        hourly, temporal_info = hourly_profile(data)
        result["hourly_profile"] = hourly
        report["urban_enrichment"] = {"version": URBAN_VERSION,
                                     "configuration": URBAN_CONFIG}
        report["temporal_dynamics"] = temporal_info
        display(pd.Series(temporal_info, name="value").to_frame())
        fig, axes = plt.subplots(1, 2, figsize=(13, 4), sharey=True)
        labels = {"weekday": "L–V (incluye feriados)", "weekend": "Sábado–domingo"}
        for ax, role in zip(axes, ["retiros", "arribos"]):
            for day_type, color, style in [("weekday", GREEN, "-"), ("weekend", BLUE, "--")]:
                subset = hourly[(hourly.role == role) & (hourly.day_type == day_type)]
                ax.plot(subset.hour_local, subset.events_per_calendar_day_at_hour,
                        color=color, ls=style, marker="o", ms=3, label=labels[day_type])
            ax.set(title=role.capitalize(), xlabel="Hora local de CDMX",
                   ylabel="Eventos por día de la clase y por intervalo horario",
                   xticks=list(range(0, 24, 2)))
            ax.legend()
        plt.tight_layout(); plt.show()
        display(Markdown(
            "**Resultado.** La suma horaria conserva "
            f"{temporal_info['retiros_known_endpoint_weight']:,.0f} retiros y "
            f"{temporal_info['arribos_known_endpoint_weight']:,.0f} arribos conocidos. "
            f"Se normaliza por {temporal_info['calendar_weekdays']} días L–V y "
            f"{temporal_info['calendar_weekend_days']} días de fin de semana."
        ))
        """),
        "## 5. Distancia": _section("""
        ### 4.1. Magnitud humana: residentes censales en AGEBs sin estación interna

        Se enlazan exactamente los polígonos identificados como sin estación interna
        con los totales AGEB del Censo 2020 por la llave cvegeo. Se utiliza POBTOT,
        sin sumar manzanas, municipios y AGEBs entre sí. El enlace exige unicidad
        de ambas tablas y mantiene las AGEBs sin población disponible.

        La suma corresponde a habitantes registrados en 2020 dentro de esos
        polígonos, contrastados con la red del catálogo posterior: no es una
        estimación demográfica de 2025 ni prueba ausencia de acceso caminable.
        Si existen polígonos sin población conocida, se reporta el subtotal
        documentado y el número de faltantes, nunca un cero imputado. Esta magnitud
        social complementa el Gini de infraestructura, pero no lo convierte en Gini
        poblacional ni demuestra por sí sola segregación o injusticia causal.
        """, """
        census_root = V3_DIR / "data/processed" / report["contract_id"]
        census = pd.read_parquet(census_root / "censo_ageb_2020.parquet",
                                 columns=["cvegeo", "POBTOT", "nivel_geografico"])
        population_agebs, population_summary, human_info = census_population(census, agebs)
        result["population_by_ageb"] = population_agebs
        result["population_summary"] = population_summary
        report["human_dimension"] = human_info
        display(population_summary)
        population_value = human_info["population_without_internal_station_known"]
        unknown = human_info["unknown_population_without_internal_station_agebs"]
        if population_value is None:
            human_statement = "No se dispone de población conocida para calcular el subtotal."
        else:
            human_statement = (
                f"Existen {population_value / 1_000_000:.3f} millones de habitantes "
                f"registrados en el Censo 2020 ({population_value:,}) viviendo en "
                "las AGEBs sin estación interna del catálogo analizado."
            )
        display(Markdown(
            "**Magnitud social.** " + human_statement +
            f" El subtotal no incluye población desconocida de {unknown} AGEBs. "
            "No mide distancia caminable exacta ni población actualizada a 2025."
        ))
        known_population = population_summary[population_summary.cohort != "all_polygons"].copy()
        ax = (known_population.set_index("cohort").population_total_known / 1_000_000).plot.bar(
            color=[GREEN, BLUE], figsize=(9, 4), rot=0)
        ax.set_xticklabels(["Con estación interna", "Sin estación interna"])
        ax.set(ylabel="Habitantes censales conocidos (millones, 2020)",
               title="Población registrada por presencia interna de estaciones")
        plt.tight_layout(); plt.show()
        """),
        "## 10. Golden": _section("""
        ### 9.1. Segregación modal: Metro/Metrobús frente a RTP/Trolebús

        Se construyen dist_transporte_pesado_m, exclusivamente con paradas asociadas
        a agencias METRO y MB, y dist_transporte_ligero_m, con RTP y TROLE. Los nombres
        «pesado» y «ligero» son agrupaciones operativas de este análisis, no una
        clasificación técnica del peso vehicular. CC, Cablebús, tren suburbano y
        otros modos no se incorporan a esos dos grupos.

        Las paradas se identifican mediante stop_times, trips, routes y calendar
        aceptados, restringidos a calendarios con cobertura declarada de 2025.
        Esto no reconstruye su ubicación histórica ni garantiza servicio efectivo.
        Una parada usada por ambas familias puede pertenecer a ambos conjuntos:
        se documenta el solapamiento en lugar de asignar un modo arbitrario.

        Se compara Spearman con actividad anual de las estaciones existentes.
        Una mayor magnitud describe asociación monotónica, no «verdadero impacto»
        causal en adopción individual. Persisten selección de ubicaciones, oferta,
        centralidad urbana y dependencia espacial. Los intervalos bootstrap por
        AGEB tienen las mismas limitaciones del apartado anterior.
        """, """
        modal_environment, modal_correlations, modal_info = modal_proximity(
            data["frames"], result["environment"])
        result["modal_environment"] = modal_environment
        result["modal_correlations"] = modal_correlations
        report["modal_transport"] = modal_info
        report["pending_validation"] = [
            "Monthly activity and Golden stability; station-level withdrawal/arrival imbalance"
            if item == "Monthly/hourly activity and Golden stability; withdrawals versus arrivals"
            else item for item in report["pending_validation"]
        ]
        display(modal_correlations)
        display(pd.Series(modal_info["groups"], name="eligible_stop_universe").to_frame())
        display(Markdown(
            f"**Universos.** {modal_info['stop_ids_shared_between_groups']} identificadores "
            "de parada aparecen en ambos grupos. Las correlaciones originales con todas "
            "las paradas GTFS se conservan sin modificación."
        ))
        fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
        modal_labels = {"dist_transporte_pesado_m": "Metro/Metrobús",
                        "dist_transporte_ligero_m": "RTP/Trolebús"}
        for ax, (column, label) in zip(axes, modal_labels.items()):
            sns.regplot(data=modal_environment, x=column, y="viajes_diarios_prom",
                        ax=ax, ci=None, color=GREEN, scatter_kws={"s": 12, "alpha": 0.4})
            ax.set(xlabel=f"Distancia a {label} (m)", ylabel="Actividad diaria observada",
                   title=label + ": asociación, no efecto causal")
        plt.tight_layout(); plt.show()
        """),
    }
    enriched = []
    for kind, source in get_notebook_cells():
        if kind == "markdown":
            for prefix, section in additions.items():
                if source.startswith(prefix):
                    enriched.extend(section)
            source = source.replace(
                "Quedan pendientes diagnóstico horario/mensual y estabilidad del Golden Cluster,",
                "La sección 3.1 incorpora el diagnóstico horario; quedan pendientes el análisis "
                "mensual y la estabilidad del Golden Cluster,")
        enriched.append((kind, source))
    if sum(kind == "code" for kind, _ in enriched) != 16:
        raise ValueError("Expected 13 unchanged code cells plus three urban additions")
    return enriched
