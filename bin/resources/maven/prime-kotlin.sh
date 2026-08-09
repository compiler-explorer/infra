#!/bin/bash

# Maven builds Kotlin with kotlin-maven-plugin, which drives a compiler it resolves from a repository rather than
# whatever is installed on the machine. Almost everything it resolves, a Kotlin installation already carries -- its
# jars are those artifacts, byte for byte -- and Compiler Explorer links those in at build time, which is how the
# compiler you select is the one that runs. What is left over is what this fetches, beside the compiler it belongs
# to: the plugin itself, the poms, and from Kotlin 2.2 the embeddable compiler, a repackaging with everything
# relocated inside it that no distribution ships.
#
# Kept per version rather than inside maven so that installing a new Kotlin costs one small install of its own,
# instead of repriming maven from scratch.

set -euo pipefail

VERSION="$1"
# Where to leave the repository, relative to the staging root this is run from.
OUT="$2"
MAVEN_HOME="$3"
KOTLIN_HOME="$4"
# The JDKs to try building under. They have to be named rather than discovered: an install may be sandboxed to its
# declared dependencies, with nothing else of /opt/compiler-explorer visible.
shift 4
JDKS="$*"

MVN="$MAVEN_HOME/bin/mvn"
# Everything maven itself needs is already there, and reading through to it is what keeps this install small.
SHARED_REPO="$MAVEN_HOME/repository"
REPO="$(pwd)/$OUT"
PROBE="$(pwd)/ce-prime-kotlin"
HEAD="$(pwd)/ce-verify-head"
# Where maven's own noise goes: a successful install should say one line, not a stack trace from an attempt that was
# never expected to work.
LOG="$(pwd)/ce-maven-output.log"
# What the build is to link in from the installation, which is this repository's half of the bargain.
SUPPLIED="$REPO/.ce-supplied-by-installation"

# What a Kotlin installation carries, and so what does not need keeping: Compiler Explorer supplies these from the
# selected compiler. Anything else a build resolves stays -- the plugin's own dependencies are pinned to old
# versions, kotlin-reflect 1.6.10 and trove4j among them, that no distribution has.
DISTRIBUTED_ARTIFACTS="kotlin-compiler kotlin-reflect kotlin-script-runtime kotlin-scripting-common
    kotlin-scripting-compiler kotlin-scripting-compiler-impl kotlin-scripting-jvm kotlin-stdlib kotlin-stdlib-jdk7
    kotlin-stdlib-jdk8 kotlin-daemon-client"

export JAVA_HOME="${JDKS%% *}"

# A project that uses the plugin the way a user's would, so that resolving it fetches what a real build needs.
mkdir -p "$PROBE/src/main/kotlin"
sed "s/@KOTLIN_VERSION@/$VERSION/" > "$PROBE/pom.xml" <<'POM'
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.compiler-explorer</groupId>
  <artifactId>prime-kotlin</artifactId>
  <version>1.0</version>
  <properties><kotlin.version>@KOTLIN_VERSION@</kotlin.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.jetbrains.kotlin</groupId>
      <artifactId>kotlin-stdlib</artifactId>
      <version>${kotlin.version}</version>
    </dependency>
  </dependencies>
  <build>
    <sourceDirectory>src/main/kotlin</sourceDirectory>
    <plugins>
      <plugin>
        <groupId>org.jetbrains.kotlin</groupId>
        <artifactId>kotlin-maven-plugin</artifactId>
        <version>${kotlin.version}</version>
        <executions>
          <execution><id>compile</id><phase>compile</phase><goals><goal>compile</goal></goals></execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
POM
echo 'fun main() { println(1) }' > "$PROBE/src/main/kotlin/Prime.kt"

# Where a distribution keeps the jar for an artifact: named after it, or without the leading `kotlin-`.
installation_jar() {
    local artifact="$1" candidate
    for candidate in "$KOTLIN_HOME/lib/$artifact.jar" "$KOTLIN_HOME/lib/${artifact#kotlin-}.jar"; do
        if [ -f "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

prime() {
    # Never failing, and quiet: the compilation may not manage it under this JDK -- an old Kotlin under a new one
    # cannot -- which says nothing about whether everything was fetched, and fetching is all this is for. The output
    # is kept rather than discarded, to be shown if it turns out something was not.
    (cd "$PROBE" && "$MVN" -B -q --fail-never -Dkotlin.version="$VERSION" \
        -Dmaven.repo.local="$REPO" -Dmaven.repo.local.tail="$SHARED_REPO" "$@") >> "$LOG" 2>&1 || true
}

mkdir -p "$REPO"
prime package
# Running a Kotlin program needs its standard library beside the classes, which is how a build gets at it.
prime dependency:copy-dependencies

# No plugin, no Kotlin: fail the install rather than leave a directory that looks like support for this version.
PLUGIN_JAR="$REPO/org/jetbrains/kotlin/kotlin-maven-plugin/$VERSION/kotlin-maven-plugin-$VERSION.jar"
if [ ! -f "$PLUGIN_JAR" ]; then
    cat "$LOG"
    echo "Kotlin $VERSION has no maven plugin to build with"
    exit 1
fi

# Take back out what the installation supplies, at this version only, and say which those were: guessing at it later
# from what has a pom is not good enough, because an artifact maven itself already had -- the Java plugins drag in a
# Kotlin standard library of their own -- is resolved from there and leaves no pom here to notice.
: > "$SUPPLIED"
for artifact in $DISTRIBUTED_ARTIFACTS; do
    jar="$REPO/org/jetbrains/kotlin/$artifact/$VERSION/$artifact-$VERSION.jar"
    test -f "$jar" || continue
    # Only ever remove what the installation demonstrably has, so that what is recorded here can always be answered.
    installation_jar "$artifact" > /dev/null || continue
    rm -f "$jar" "$jar.sha1"
    echo "$artifact" >> "$SUPPLIED"
done

# Linked the way Compiler Explorer will link it, from that same record.
rm -rf "$HEAD"
while read -r artifact; do
    mkdir -p "$HEAD/org/jetbrains/kotlin/$artifact/$VERSION"
    ln -s "$(installation_jar "$artifact")" "$HEAD/org/jetbrains/kotlin/$artifact/$VERSION/$artifact-$VERSION.jar"
done < "$SUPPLIED"

# Prove it offline against the chain a build will use, under whichever JDK manages it: Compiler Explorer pairs each
# Kotlin with a JDK of its era -- 1.4 with 15, 2.1 with 23 -- so an old compiler failing under a new JDK says nothing.
# Where the machine is not sandboxed, anything else installed is worth trying too.
built_with=""
for jdk in $JDKS $(ls -d /opt/compiler-explorer/jdk-* 2>/dev/null | sort -Vr); do
    test -x "$jdk/bin/java" || continue
    rm -rf ce-verify
    cp -r "$PROBE" ce-verify
    rm -rf ce-verify/target
    : > "$LOG"
    if (cd ce-verify && JAVA_HOME="$jdk" "$MVN" -o -B -q -Dkotlin.version="$VERSION" \
            -Dmaven.repo.local="$HEAD" -Dmaven.repo.local.tail="$REPO,$SHARED_REPO" package) >> "$LOG" 2>&1; then
        built_with="$(basename "$jdk")"
        break
    fi
done
rm -rf "$PROBE" "$HEAD" ce-verify

if [ -z "$built_with" ]; then
    # The last attempt's output, so that a version being dropped comes with the reason it was.
    cat "$LOG"
    echo "Kotlin $VERSION cannot build under any JDK here"
    exit 1
fi
rm -f "$LOG"
echo "Verified an offline Kotlin $VERSION build against the installed compiler, under $built_with"
