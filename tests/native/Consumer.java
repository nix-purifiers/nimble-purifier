import java.lang.foreign.*;
import java.lang.invoke.*;
import java.nio.file.*;

public class Consumer {
  public static void main(String[] args) throws Throwable {
    Path expected = Path.of(args[0]).toRealPath();
    int value = Integer.parseInt(args[2]);
    Linker linker = Linker.nativeLinker();
    SymbolLookup lib = SymbolLookup.libraryLookup(expected, Arena.global());
    MethodHandle init = linker.downcallHandle(lib.find(args[1]).orElseThrow(), FunctionDescriptor.ofVoid());
    init.invokeExact();
    MemorySegment symbol = lib.find("nimAnswer").orElseThrow();
    MethodHandle answer = linker.downcallHandle(symbol, FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));
    if ((int) answer.invokeExact(0) != value || (int) answer.invokeExact(1) != value + 2) throw new AssertionError("values");
    try (Arena infoArena = Arena.ofConfined()) {
      MemorySegment info = infoArena.allocate(4 * ValueLayout.ADDRESS.byteSize(), ValueLayout.ADDRESS.byteAlignment());
      MethodHandle origin = linker.downcallHandle(linker.defaultLookup().find("dladdr").orElseThrow(),
        FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS, ValueLayout.ADDRESS));
      if ((int) origin.invokeExact(symbol, info) == 0) throw new AssertionError("dladdr");
      if (!Path.of(info.get(ValueLayout.ADDRESS, 0).reinterpret(4096).getString(0)).toRealPath().equals(expected))
        throw new AssertionError("origin");
    }
    System.out.println("[" + value + ", " + (value + 2) + "]");
  }
}
