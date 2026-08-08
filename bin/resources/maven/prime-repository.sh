#!/bin/bash

# Maven cannot do anything without its plugins, and build nodes have no network to fetch them: even a hello world
# needs the resources, compiler and jar plugins. So prime a repository here, while we still have a network, by running
# each plugin against a throwaway project -- a plugin only downloads what it needs when actually invoked. Builds then
# point maven.repo.local at the result; it is only read, so all compilations share this one copy.
#
# This is the Java half, and it is all of it: what a Kotlin version needs on top is installed beside that compiler
# instead, by prime-kotlin.sh, so that adding a Kotlin never means priming this again. See tools/kotlin-maven in
# kotlin.yaml.

set -euo pipefail

# The unpacked maven, relative to the staging root this is run from, and the JDK to run it with.
MVN_DIR="$1"
export JAVA_HOME="$2"

REPO="$(pwd)/$MVN_DIR/repository"
MVN="$(pwd)/$MVN_DIR/bin/mvn"

prime() {
    # Never failing: some of these exit non-zero by design -- checkstyle on a style violation -- while still having
    # fetched everything they need.
    "$MVN" -B -q --fail-never -Dmaven.repo.local="$REPO" "$@" || true
}

verify_offline() {
    # Priming is best-effort, so prove the result actually serves an offline build before shipping it.
    "$MVN" -o -B -Dmaven.repo.local="$REPO" clean package
}

mkdir -p ce-prime/src/main/java
cat > ce-prime/pom.xml <<'POM'
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.compiler-explorer</groupId>
  <artifactId>prime</artifactId>
  <version>1.0</version>
  <build><plugins>
    <plugin><groupId>org.codehaus.mojo</groupId><artifactId>exec-maven-plugin</artifactId><version>3.5.0</version></plugin>
    <plugin><groupId>org.codehaus.mojo</groupId><artifactId>build-helper-maven-plugin</artifactId><version>3.6.0</version></plugin>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-checkstyle-plugin</artifactId><version>3.6.0</version></plugin>
    <plugin><groupId>com.diffplug.spotless</groupId><artifactId>spotless-maven-plugin</artifactId><version>2.44.4</version></plugin>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-javadoc-plugin</artifactId><version>3.11.2</version></plugin>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-source-plugin</artifactId><version>3.3.1</version></plugin>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-dependency-plugin</artifactId><version>3.8.1</version></plugin>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-antrun-plugin</artifactId><version>3.1.0</version></plugin>
  </plugins></build>
</project>
POM
echo 'public class Prime { public static void main(String[] a) { System.out.println(1); } }' > ce-prime/src/main/java/Prime.java

pushd ce-prime > /dev/null
# One at a time: a plugin that stops the chain leaves everything after it unfetched.
prime clean install
prime javadoc:jar
prime source:jar
prime exec:java -Dexec.mainClass=Prime
prime spotless:check
prime checkstyle:check
prime antrun:run
prime build-helper:add-source
prime dependency:list
prime dependency:copy-dependencies
# A plugin that runs inside maven drags in a maven API of its own era, and kotlin-maven-plugin does: three of them
# across the versions Compiler Explorer offers, at some 13 MiB each. They have nothing to do with which Kotlin asked
# for them, so they belong here rather than in every per-version repository, which would each carry a copy.
for maven_api in 2.2.1 3.0 3.0.5; do
    prime org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get -Dartifact="org.apache.maven:maven-core:$maven_api"
done
verify_offline
popd > /dev/null
rm -rf ce-prime

# Last, so that a prime that fell over never looks finished. Bump the number when what is primed here changes: it is
# what tells an install predating that change to redo itself.
touch "$REPO/.ce-primed-2"
