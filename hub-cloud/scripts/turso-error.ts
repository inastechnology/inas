type TursoHttpError = Error & {
  status: number;
};

export function isTursoHttpError(error: unknown, status: number): error is TursoHttpError {
  return (
    error instanceof Error &&
    error.name === "TursoClientError" &&
    "status" in error &&
    error.status === status
  );
}
