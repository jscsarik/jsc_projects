"""League points include a separate, idempotent special-event ledger."""
def standings(connection,season):
    return tuple(dict(r) for r in connection.execute('''SELECT a.id AS agency_id,a.name,
        COALESCE(r.played,0) AS played,COALESCE(r.wins,0) AS wins,COALESCE(r.losses,0) AS losses,
        COALESCE(r.points,0)+COALESCE(s.points,0)+COALESCE(f.points,0) AS points,
        COALESCE(r.points,0) AS regular_points,COALESCE(s.points,0) AS special_points
        FROM agencies a LEFT JOIN regular_standings r ON r.agency_id=a.id AND r.season=?
        LEFT JOIN special_standings s ON s.agency_id=a.id AND s.season=?
        LEFT JOIN (SELECT agency_id,season,SUM(delta) AS points FROM finance_points GROUP BY agency_id,season) f
        ON f.agency_id=a.id AND f.season=?
        ORDER BY points DESC,a.id''',(season,season,season)))
