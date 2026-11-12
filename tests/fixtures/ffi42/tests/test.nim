import results
let value = Result[int, string].ok(42)
doAssert value.get() == 42
echo "locked task dependency"
