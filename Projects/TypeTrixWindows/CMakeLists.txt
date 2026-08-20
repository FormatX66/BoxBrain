cmake_minimum_required(VERSION 3.20)
project(TypeTrixWindows LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(typetrix_core
    core/friction_detector.cpp
)

target_include_directories(typetrix_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)

add_executable(typetrix_core_tests
    tests/friction_detector_tests.cpp
)

target_link_libraries(typetrix_core_tests PRIVATE typetrix_core)

enable_testing()
add_test(NAME typetrix_core_tests COMMAND typetrix_core_tests)

if(WIN32)
  add_subdirectory(windows/tsf)
endif()
