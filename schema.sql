CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY NOT NULL,
    date TEXT NOT NULL,
    area TEXT NOT NULL,
    description TEXT NOT NULL,
    amount TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Aprovado', 'Pendente', 'Cancelado'))
);
