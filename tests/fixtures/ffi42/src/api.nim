import results

{.compile: "owned-helper.c".}
proc ownedOffset(input: cint): cint {.importc, header: "owned-helper.h".}

let initial = Result[seq[int], string].ok(@[42])

proc nimAnswer(input: cint): cint {.cdecl, exportc, dynlib.} =
  let values = initial.get()
  cint(values[0] + int(ownedOffset(input)))
