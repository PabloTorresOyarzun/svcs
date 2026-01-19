# ETAPA 1: Compilar Go
FROM golang:1.21-bullseye AS builder

WORKDIR /app

# 1. Copiamos TODO de una vez (go.mod y main.go)
# Así evitamos problemas de capas intermedias
COPY . .

# 2. Generamos el go.sum y descargamos dependencias aquí mismo
RUN go mod tidy

# 3. Compilar binario estático
# AGREGADO: "-mod=mod" -> Esto obliga a Go a actualizar dependencias al vuelo si falta algo
RUN CGO_ENABLED=0 GOOS=linux go build -mod=mod -a -installsuffix cgo -o migrator main.go

# ETAPA 2: Imagen final ultra-ligera (Alpine)
FROM alpine:latest

WORKDIR /root/

# Instalar certificados CA para que SSL funcione si es necesario
RUN apk --no-cache add ca-certificates tzdata
ENV TZ=America/Santiago

# Copiar el binario desde la etapa de construcción
COPY --from=builder /app/migrator .

# Ejecutar
CMD ["./migrator"]