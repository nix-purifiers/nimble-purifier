import results
proc answer*(offset: int): int {.exportc: "nimAnswer".} =
  let value = Result[int, string].ok(43 + offset * 2)
  result = value.get()
{.emit: "globalThis.nimAnswer = `answer`;".}
