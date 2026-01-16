package main

import (
	"database/sql"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	_ "github.com/denisenkom/go-mssqldb"
	_ "github.com/lib/pq"
)

// --- CONFIGURACION OPTIMA ---
const (
	MaxWorkers = 30    // 30 es el punto dulce para tu hardware
	BatchSize  = 25000 
	MaxRetries = 10
)

var SourceDBs = []string{"vin", "exportacion", "exportasis", "siscon", "BD_FACTURA", "declaracion"}

type ForeignKeySQL struct {
	ConstraintName string
	SQL            string
}

func main() {
	log.Println("[INFO] Iniciando Migracion FINAL (Strict Types + TrimSpaces + High Performance)...")

	required := []string{"PG_HOST", "MSSQL_HOST", "MSSQL_PASS"}
	for _, v := range required {
		if os.Getenv(v) == "" {
			log.Fatalf("[FATAL] Falta variable de entorno: %s", v)
		}
	}

	// Connection String sin options raros para evitar error de driver
	pgConnStr := fmt.Sprintf("host=%s port=%s user=%s password=%s dbname=%s sslmode=disable binary_parameters=yes",
		os.Getenv("PG_HOST"), os.Getenv("PG_PORT"), os.Getenv("PG_USER"), os.Getenv("PG_PASS"), os.Getenv("PG_DB"))

	for _, dbName := range SourceDBs {
		processDatabase(dbName, pgConnStr)
	}
	log.Println("[INFO] Migracion Completa Finalizada.")
}

func isIgnoredTable(tableName string) bool {
	t := strings.ToLower(tableName)
	if t == "dtproperties" || t == "sysdiagrams" || t == "systranschemas" { return true }
	if strings.HasSuffix(t, "_ct") || strings.Contains(t, "_ct_") { return true }
	ignoredList := map[string]bool{
		"change_tables": true, "ddl_history": true, "lsn_time_mapping": true,
		"captured_columns": true, "index_columns": true, "comandos": true,
	}
	return ignoredList[t]
}

func getPostgresType(mssqlType string, precision, scale int64) string {
	t := strings.ToUpper(mssqlType)
	switch t {
	case "TINYINT", "SMALLINT":
		return "SMALLINT"
	case "INT", "INTEGER":
		return "INTEGER"
	case "BIGINT":
		return "BIGINT"
	case "BIT":
		return "BOOLEAN"
	case "REAL":
		return "REAL"
	case "FLOAT":
		return "DOUBLE PRECISION"
	case "DECIMAL", "NUMERIC", "MONEY", "SMALLMONEY":
		if precision > 0 {
			return fmt.Sprintf("NUMERIC(%d, %d)", precision, scale)
		}
		return "NUMERIC"
	case "DATE":
		return "DATE"
	case "DATETIME", "DATETIME2", "SMALLDATETIME":
		return "TIMESTAMP"
	case "TIME":
		return "TIME"
	case "CHAR", "NCHAR", "VARCHAR", "NVARCHAR", "TEXT", "NTEXT", "SYSNAME":
		return "TEXT"
	case "BINARY", "VARBINARY", "IMAGE", "TIMESTAMP_SQL": 
		return "BYTEA"
	case "UNIQUEIDENTIFIER":
		return "UUID"
	default:
		return "TEXT"
	}
}

func processDatabase(dbName, pgConnStr string) {
	log.Printf("[INFO] --- INICIANDO DB: %s ---", dbName)

	pgDB, err := sql.Open("postgres", pgConnStr)
	if err != nil {
		log.Fatalf("[FATAL] Error conectando a PG: %v", err)
	}
	pgDB.SetMaxOpenConns(MaxWorkers + 10)
	pgDB.SetMaxIdleConns(MaxWorkers + 10)
	
	// OPTIMIZACION DE VELOCIDAD
	if _, err := pgDB.Exec("SET synchronous_commit TO OFF"); err != nil {
		log.Printf("[WARN] No se pudo desactivar synchronous_commit: %v", err)
	}

	defer pgDB.Close()

	_, err = pgDB.Exec(fmt.Sprintf(`CREATE SCHEMA IF NOT EXISTS "%s"`, dbName))
	if err != nil {
		log.Printf("[WARN] Error creando esquema: %v", err)
	}

	mssqlConnStr := fmt.Sprintf("server=%s;port=%s;user id=%s;password=%s;database=%s;encrypt=disable;keepAlive=30",
		os.Getenv("MSSQL_HOST"), os.Getenv("MSSQL_PORT"), os.Getenv("MSSQL_USER"), os.Getenv("MSSQL_PASS"), dbName)

	mssqlDB, err := sql.Open("mssql", mssqlConnStr)
	if err != nil {
		log.Printf("[ERROR] Error conectando a MSSQL: %v", err)
		return
	}
	mssqlDB.SetMaxOpenConns(MaxWorkers + 10)
	mssqlDB.SetMaxIdleConns(MaxWorkers + 10)
	defer mssqlDB.Close()

	rows, err := mssqlDB.Query("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
	if err != nil {
		log.Printf("[ERROR] Error listando tablas: %v", err)
		return
	}
	
	var tables []string
	for rows.Next() {
		var t string
		rows.Scan(&t)
		
		// --- FIX IMPORTANTE: ELIMINAR ESPACIOS ---
		t = strings.TrimSpace(t) 
		// -----------------------------------------

		if !isIgnoredTable(t) {
			tables = append(tables, t)
		}
	}
	rows.Close()

	log.Printf("[INFO] Encontradas %d tablas. Iniciando carga masiva...", len(tables))

	fkChannel := make(chan []ForeignKeySQL, len(tables))
	jobs := make(chan string, len(tables))
	var wg sync.WaitGroup

	for w := 1; w <= MaxWorkers; w++ {
		wg.Add(1)
		go worker(w, dbName, mssqlDB, pgDB, jobs, fkChannel, &wg)
	}

	for _, t := range tables {
		jobs <- t
	}
	close(jobs)

	wg.Wait()
	close(fkChannel)

	log.Println("[INFO] Aplicando Foreign Keys...")
	applyForeignKeys(pgDB, fkChannel)
}

func worker(id int, schema string, ms *sql.DB, pg *sql.DB, jobs <-chan string, fkChan chan<- []ForeignKeySQL, wg *sync.WaitGroup) {
	defer wg.Done()
	for table := range jobs {
		fks := migrateTable(schema, table, ms, pg)
		if len(fks) > 0 {
			fkChan <- fks
		}
	}
}

func migrateTable(schema, table string, ms *sql.DB, pg *sql.DB) []ForeignKeySQL {
	var rows *sql.Rows
	var err error

	for attempt := 1; attempt <= MaxRetries; attempt++ {
		rows, err = ms.Query(fmt.Sprintf("SELECT * FROM [%s]", table))
		if err == nil { break }
		time.Sleep(time.Duration(attempt) * 500 * time.Millisecond)
	}
	if err != nil {
		log.Printf("[ERROR] [FINAL] %s: No se pudo leer origen: %v", table, err)
		return nil
	}
	defer rows.Close()

	cols, _ := rows.Columns()
	colTypes, _ := rows.ColumnTypes()

	pg.Exec(fmt.Sprintf(`DROP TABLE IF EXISTS "%s"."%s" CASCADE`, schema, table))
	
	createSQL := fmt.Sprintf(`CREATE TABLE "%s"."%s" (`, schema, table)
	for i, c := range cols {
		pgType := "TEXT"
		if i < len(colTypes) {
			precision, scale, _ := colTypes[i].DecimalSize()
			pgType = getPostgresType(colTypes[i].DatabaseTypeName(), precision, scale)
		}
		// Limpiamos tambien los nombres de columnas por si acaso
		safeCol := strings.TrimSpace(strings.ReplaceAll(c, "\"", ""))
		createSQL += fmt.Sprintf(`"%s" %s`, safeCol, pgType)
		if i < len(cols)-1 {
			createSQL += ", "
		}
	}
	createSQL += ")"

	if _, err := pg.Exec(createSQL); err != nil {
		log.Printf("[ERROR] %s: Fallo create table: %v", table, err)
		return nil
	}

	values := make([]interface{}, len(cols))
	scanArgs := make([]interface{}, len(cols))
	for i := range values {
		scanArgs[i] = &values[i]
	}

	tx, _ := pg.Begin()
	tx.Exec("SET synchronous_commit TO OFF") // Optimizacion por transaccion

	var count int64 = 0
	placeholders := make([]string, len(cols))
	for i := range placeholders { placeholders[i] = fmt.Sprintf("$%d", i+1) }
	insertQ := fmt.Sprintf(`INSERT INTO "%s"."%s" VALUES (%s)`, schema, table, strings.Join(placeholders, ","))
	stmt, _ := tx.Prepare(insertQ)
	defer stmt.Close()

	for rows.Next() {
		if err := rows.Scan(scanArgs...); err != nil { continue }
		
		finalVals := make([]interface{}, len(cols))
		for i, v := range values {
			if v == nil {
				finalVals[i] = nil
			} else {
				typeName := ""
				if i < len(colTypes) { typeName = strings.ToUpper(colTypes[i].DatabaseTypeName()) }

				switch t := v.(type) {
				case []byte:
					if typeName == "BIT" || typeName == "BOOLEAN" {
						if len(t) > 0 && t[0] == 1 { finalVals[i] = true } else { finalVals[i] = false }
					} else if typeName == "UNIQUEIDENTIFIER" {
						if len(t) == 16 {
							finalVals[i] = fmt.Sprintf("%x-%x-%x-%x-%x", t[0:4], t[4:6], t[6:8], t[8:10], t[10:])
						} else {
							finalVals[i] = nil
						}
					} else if strings.Contains(typeName, "BINARY") || strings.Contains(typeName, "IMAGE") {
						finalVals[i] = t
					} else {
						strVal := string(t)
						finalVals[i] = strings.ReplaceAll(strVal, "\x00", "")
					}
				case string:
					finalVals[i] = strings.ReplaceAll(t, "\x00", "")
				case bool:
					finalVals[i] = t
				default:
					finalVals[i] = v
				}
			}
		}

		if _, err := stmt.Exec(finalVals...); err != nil {
			// Silencioso
		}

		count++
		if count%BatchSize == 0 {
			tx.Commit()
			tx, _ = pg.Begin()
			tx.Exec("SET synchronous_commit TO OFF")
			stmt, _ = tx.Prepare(insertQ)
		}
	}
	tx.Commit()

	pkCols := getPrimaryKeyColumns(ms, table)
	if len(pkCols) > 0 {
		pkName := fmt.Sprintf("pk_%s_%s", schema, table)
		if len(pkName) > 63 { pkName = pkName[:63] }
		colsStr := strings.Join(pkCols, `", "`)
		pg.Exec(fmt.Sprintf(`ALTER TABLE "%s"."%s" ADD CONSTRAINT "%s" PRIMARY KEY ("%s")`, schema, table, pkName, colsStr))
	}

	if count > 0 {
		log.Printf("[OK] %s: %d filas", table, count)
	}

	return getForeignKeys(ms, schema, table)
}

func getPrimaryKeyColumns(db *sql.DB, tableName string) []string {
	query := `SELECT c.name FROM sys.indexes i INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id INNER JOIN sys.columns c ON ic.object_id = c.object_id AND c.column_id = ic.column_id INNER JOIN sys.objects o ON i.object_id = o.object_id WHERE i.is_primary_key = 1 AND o.name = @p1 ORDER BY ic.key_ordinal`
	rows, err := db.Query(query, tableName)
	if err != nil { return nil }
	defer rows.Close()
	var pks []string
	for rows.Next() {
		var col string
		rows.Scan(&col)
		pks = append(pks, col)
	}
	return pks
}

func getForeignKeys(db *sql.DB, schema, tableName string) []ForeignKeySQL {
	query := `SELECT obj.name, col1.name, tab2.name, col2.name FROM sys.foreign_key_columns fkc INNER JOIN sys.objects obj ON obj.object_id = fkc.constraint_object_id INNER JOIN sys.tables tab1 ON tab1.object_id = fkc.parent_object_id INNER JOIN sys.columns col1 ON col1.column_id = fkc.parent_column_id AND col1.object_id = tab1.object_id INNER JOIN sys.tables tab2 ON tab2.object_id = fkc.referenced_object_id INNER JOIN sys.columns col2 ON col2.column_id = fkc.referenced_column_id AND col2.object_id = tab2.object_id WHERE tab1.name = @p1`
	rows, err := db.Query(query, tableName)
	if err != nil { return nil }
	defer rows.Close()
	var fks []ForeignKeySQL
	for rows.Next() {
		var fkName, col, refTable, refCol string
		if err := rows.Scan(&fkName, &col, &refTable, &refCol); err == nil {
			pgFkName := fmt.Sprintf("fk_%s_%s_%s", tableName, col, refTable)
			if len(pgFkName) > 63 { pgFkName = pgFkName[:63] }
			sql := fmt.Sprintf(`ALTER TABLE "%s"."%s" ADD CONSTRAINT "%s" FOREIGN KEY ("%s") REFERENCES "%s"."%s" ("%s")`, schema, tableName, pgFkName, col, schema, refTable, refCol)
			fks = append(fks, ForeignKeySQL{ConstraintName: pgFkName, SQL: sql})
		}
	}
	return fks
}

func applyForeignKeys(pg *sql.DB, fkChan <-chan []ForeignKeySQL) {
	var allFks []ForeignKeySQL
	for fks := range fkChan { allFks = append(allFks, fks...) }
	log.Printf("[INFO] Procesando %d FKs...", len(allFks))
	for _, fk := range allFks { pg.Exec(fk.SQL) }
}